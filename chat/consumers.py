import json
from django.core.serializers.json import DjangoJSONEncoder
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Conversation, Message, ChatBlock
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.user = self.scope['user']

        # Reject connection if user is anonymous
        if self.user.is_anonymous:
            await self.close()
            return

        # Resolve conversation instance
        self.conversation = await self.get_or_create_conversation(self.conversation_id)
        if not self.conversation:
            await self.close()
            return

        # Use the actual UUID for the group name
        self.room_group_name = f'chat_{self.conversation.id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WS Accepted: Profile {self.user.email} joined conversation {self.conversation_id}")

        # Check and broadcast block status on connection
        block_status = await self.get_block_status()
        if block_status:
            await self.send(text_data=json.dumps(block_status, cls=DjangoJSONEncoder))

        # Broadcast online status
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_status',
                'status_data': {
                    'type': 'presence',
                    'user_id': str(self.user.id),
                    'status': 'online'
                }
            }
        )

    async def disconnect(self, close_code):
        # Broadcast offline status (only if was joined and authenticated and room joined)
        if hasattr(self, 'user') and not self.user.is_anonymous and hasattr(self, 'room_group_name'):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_status',
                    'status_data': {
                        'type': 'presence',
                        'user_id': str(self.user.id),
                        'status': 'offline'
                    }
                }
            )
            print(f"WS Disconnected: Profile {self.user.email} left conversation {self.conversation_id}")

        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'message') # Default to message

        if message_type == 'typing':
            is_typing = data.get('is_typing', False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_status',
                    'status_data': {
                        'type': 'typing',
                        'user_id': str(self.user.id),
                        'is_typing': is_typing
                    }
                }
            )
            return

        if message_type == 'message_status':
            message_id = data.get('message_id')
            status = data.get('status')
            
            updated = await self.update_message_status(message_id, status)
            if updated:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_status',
                        'status_data': {
                            'type': 'message_status',
                            'message_id': message_id,
                            'status': status
                        }
                    }
                )
            return

        if message_type == 'delete_message':
            message_id = data.get('message_id')
            deleted = await self.delete_message_from_db(message_id)
            if deleted:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_status',
                        'status_data': {
                            'type': 'delete_message',
                            'message_id': message_id
                        }
                    }
                )
            return

        if message_type == 'update_message':
            message_id = data.get('message_id')
            new_content = data.get('message')
            updated_msg = await self.update_message_in_db(message_id, new_content)
            if updated_msg:
                serialized = await self.get_serialized_chat_message(updated_msg, self.conversation_id)
                serialized = json.loads(json.dumps(serialized, cls=DjangoJSONEncoder))
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_status',
                        'status_data': {
                            'type': 'update_message',
                            'message': serialized
                        }
                    }
                )
            return

        if not self.user.is_authenticated:
            return

        # Check if the conversation is blocked before saving
        is_blocked = await self.is_conversation_blocked()
        if is_blocked:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'This conversation is blocked. You cannot send messages.'
            }))
            return
            
        # Save message to database and get full object
        try:
            message_obj = await self.save_message(self.user, data)
            
            # Trigger persistent notification for the receiver
            receiver = await self.get_receiver(message_obj)
            if receiver:
                await self.trigger_notification(receiver, message_obj)

            # Serialize the message and participants for the frontend
            serialized_chat_message = await self.get_serialized_chat_message(message_obj, self.conversation_id)
            # Sanitize UUIDs to strings for Channel Layer compatibility
            serialized_chat_message = json.loads(json.dumps(serialized_chat_message, cls=DjangoJSONEncoder))

            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'chat_message_data': serialized_chat_message
                }
            )
        except Exception as e:
            print(f"Error processing WS message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to save or send message. Please try again.'
            }))

    # Receive message from room group
    async def chat_message(self, event):
        chat_message_data = event['chat_message_data']
        # Add type for frontend discrimination
        chat_message_data['type'] = 'message'
        await self.send(text_data=json.dumps(chat_message_data, cls=DjangoJSONEncoder))

    # Receive status update from room group
    async def chat_status(self, event):
        status_data = event['status_data']
        await self.send(text_data=json.dumps(status_data, cls=DjangoJSONEncoder))

    @database_sync_to_async
    def update_message_status(self, message_id, status):
        try:
            msg = Message.objects.get(id=message_id)
            if msg.sender.id == self.user.id:
                return False
            
            updated = False
            if status == 'delivered' and not msg.is_delivered:
                msg.is_delivered = True
                updated = True
            elif status == 'seen' and not msg.is_seen:
                msg.is_delivered = True
                msg.is_seen = True
                updated = True
                
            if updated:
                msg.save(update_fields=['is_delivered', 'is_seen'])
            return updated
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def delete_message_from_db(self, message_id):
        try:
            msg = Message.objects.get(id=message_id, sender=self.user)
            msg.delete()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def update_message_in_db(self, message_id, new_content):
        try:
            msg = Message.objects.get(id=message_id, sender=self.user)
            msg.message = new_content
            msg.content = new_content
            msg.save(update_fields=['message', 'content'])
            return msg
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def get_receiver(self, message_obj):
        return message_obj.conversation.participants.exclude(id=message_obj.sender.id).first()

    @database_sync_to_async
    def trigger_notification(self, user, message_obj):
        from notifications.utils import send_notification
        send_notification(
            user=user,
            sender=message_obj.sender,
            title=f"New Message",
            message=message_obj.message or "You have a new message",
            notification_type="MESSAGE",
            data={
                "conversation_id": str(self.conversation.id),
                "sender_id": str(message_obj.sender.id)
            }
        )

    @database_sync_to_async
    def get_serialized_chat_message(self, message_obj, original_id=None):
        from chat.serializers import MessageSerializer
        from accounts.serializers import ProfileSerializer
        
        message_data = MessageSerializer(message_obj, context={'original_id': original_id}).data
        sender_profile = ProfileSerializer(message_obj.sender.profile).data
        
        receiver = message_obj.conversation.participants.exclude(id=message_obj.sender.id).first()
        receiver_profile = ProfileSerializer(receiver.profile).data if receiver else None
        
        return {
            'message': message_data,
            'sender': sender_profile,
            'receiver': receiver_profile
        }

    @database_sync_to_async
    def get_or_create_conversation(self, conversation_id):
        try:
            import uuid
            val = uuid.UUID(conversation_id, version=4)
            return Conversation.objects.filter(id=val).first()
        except ValueError:
            if '_' in conversation_id:
                uids = conversation_id.split('_')
                if len(uids) == 2:
                    try:
                        user1 = User.objects.get(id=uids[0])
                        user2 = User.objects.get(id=uids[1])
                        
                        conversation = Conversation.objects.filter(participants=user1).filter(participants=user2).first()
                        if not conversation:
                            conversation = Conversation.objects.create()
                            conversation.participants.add(user1, user2)
                        return conversation
                    except User.DoesNotExist:
                        return None
            return None

    @database_sync_to_async
    def save_message(self, user, data):
        img_file = None
        if data.get('image'):
            try:
                import base64
                from django.core.files.base import ContentFile
                img_data = base64.b64decode(data['image'])
                file_name = data.get('filename') or 'image.jpg'
                img_file = ContentFile(img_data, name=file_name)
            except Exception:
                pass

        return Message.objects.create(
            conversation=self.conversation,
            sender=user,
            content=data.get('message', '') or '',
            message=data.get('message', '') or '',
            is_calender=data.get('is_calender') or False,
            with_image=data.get('with_image') or False,
            with_image_and_text=data.get('with_image_and_text') or False,
            calender_date=data.get('calender_date'),
            media_url=data.get('media_url'),
            image=img_file,
            file_name=data.get('filename')
        )

    @database_sync_to_async
    def is_conversation_blocked(self):
        """Check if there is an active block in this conversation."""
        return ChatBlock.objects.filter(
            conversation=self.conversation
        ).exists()

    @database_sync_to_async
    def get_block_status(self):
        """Return block status data if a block exists, else None."""
        block = ChatBlock.objects.filter(
            conversation=self.conversation
        ).first()
        if block:
            return {
                'type': 'block_status',
                'blocker_id': str(block.blocker.id),
                'blocked_id': str(block.blocked.id),
                'is_blocked': True,
            }
        return None

class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if self.user.is_anonymous:
            await self.close()
            return
        
        await self.accept()
        await self.set_online_status(True)
        print(f"Global Presence WS: Profile {self.user.email} is online")
        
        # Broadcast online status to all active conversations
        conversations = await self.get_user_conversations()
        for conv_id in conversations:
            await self.channel_layer.group_send(f"chat_{conv_id}", {
                'type': 'chat_status',
                'status_data': { 'type': 'presence', 'user_id': str(self.user.id), 'status': 'online' }
            })

    async def disconnect(self, close_code):
        if not self.user.is_anonymous:
            await self.set_online_status(False)
            print(f"Global Presence WS: Profile {self.user.email} is offline")
            
            conversations = await self.get_user_conversations()
            for conv_id in conversations:
                await self.channel_layer.group_send(f"chat_{conv_id}", {
                    'type': 'chat_status',
                    'status_data': { 'type': 'presence', 'user_id': str(self.user.id), 'status': 'offline' }
                })
                
    async def receive(self, text_data):
        pass # Ignore incoming messages on this global presence socket for now

    @database_sync_to_async
    def set_online_status(self, is_online):
        try:
            profile = self.user.profile
            profile.is_online = is_online
            profile.save(update_fields=['is_online', 'last_seen'])
        except Exception:
            pass

    @database_sync_to_async
    def get_user_conversations(self):
        return list(self.user.conversations.values_list('id', flat=True))
