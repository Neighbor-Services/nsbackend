from rest_framework import viewsets, permissions
from rest_framework.response import Response
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer

class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        from django.db.models import Prefetch
        return Conversation.objects.filter(participants=self.request.user).prefetch_related(
            'participants',
            Prefetch('messages', queryset=Message.objects.order_by('created_at'))
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(self._wrap_conversations(serializer.data, request))

        serializer = self.get_serializer(queryset, many=True)
        return Response(self._wrap_conversations(serializer.data, request))

    from rest_framework.decorators import action
    @action(detail=False, methods=['post'], url_path='set_seen')
    def set_seen(self, request):
        receiver_id = request.data.get('receiver_id')
        if not receiver_id:
            return Response({"error": "receiver_id is required"}, status=400)
        
        # Mark all messages as seen in conversations between me and the receiver
        # where the current user is NOT the sender.
        Message.objects.filter(
            conversation__participants=request.user,
            is_seen=False
        ).filter(
            conversation__participants=receiver_id
        ).exclude(sender=request.user).update(is_seen=True)
        
        return Response({"status": "success"})

    def _wrap_conversations(self, data, request):
        from accounts.models import Profile
        from accounts.serializers import ProfileSerializer
        
        wrapped = []
        for conv_data in data:
            conv_id = conv_data['id']
            participants_ids = conv_data['participants']
            me_id = str(request.user.id)
            # Find the other participant's ID
            other_id = next((pid for pid in participants_ids if str(pid) != me_id), None)
            
            me_profile = Profile.objects.filter(user_id=me_id).first()
            other_profile = Profile.objects.filter(user_id=other_id).first() if other_id else None
            
            # Calculate unread count for current user
            messages_list = conv_data.get('messages', [])
            unread_count = 0
            for msg in messages_list:
                if not msg.get('is_seen', False) and str(msg.get('sender')) != me_id:
                    unread_count += 1

            chat_data = {
                "id": conv_id,
                "chat_room": conv_id,
                "user1": me_id,
                "user2": other_id,
                "unread_count": unread_count,
                "created_at": conv_data.get('created_at'),
                "updated_at": conv_data.get('updated_at'),
                "last_message": messages_list[-1] if messages_list else None,
            }
            
            wrapped.append({
                "chat": chat_data,
                "me": ProfileSerializer(me_profile, context={'request': request}).data if me_profile else None,
                "other": ProfileSerializer(other_profile, context={'request': request}).data if other_profile else None,
            })
        return wrapped

class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.select_related('sender', 'conversation').all()
    serializer_class = MessageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # Only return messages from conversations the user is a participant of
        return self.queryset.filter(conversation__participants=self.request.user).order_by('created_at')

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Filter by conversation if provided
        conversation_param = self.request.query_params.get('conversation')
        if conversation_param:
            conversation = self._get_conversation(conversation_param, request.user)
            if conversation:
                queryset = queryset.filter(conversation=conversation)
            else:
                queryset = queryset.none()
            
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'original_id': conversation_param, 'request': request})
            wrapped_data = self._wrap_messages(serializer.data, request)
            return self.get_paginated_response(wrapped_data)

        serializer = self.get_serializer(queryset, many=True, context={'original_id': conversation_param, 'request': request})
        return Response(self._wrap_messages(serializer.data, request))

    def _get_conversation(self, conversation_id, user):
        import uuid
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # 1. Try as UUID (Conversation ID)
        # 1. Try as UUID (Conversation ID)
        try:
            val = uuid.UUID(conversation_id, version=4)
            conv = Conversation.objects.filter(id=val, participants=user).first()
            if conv:
                return conv
            # If valid UUID but no conversation found, might be a User ID, so fall through.
        except ValueError:
            pass

        # 2. Try as user1_user2 pattern
        if '_' in conversation_id:
            uids = conversation_id.split('_')
            if len(uids) == 2:
                try:
                    u1 = User.objects.get(id=uids[0])
                    u2 = User.objects.get(id=uids[1])
                    if user in [u1, u2]:
                        return Conversation.objects.filter(participants=u1).filter(participants=u2).first()
                except (User.DoesNotExist, ValueError):
                    pass
        
        # 3. Try as Other User ID
        try:
            other_user = User.objects.get(id=conversation_id)
            return Conversation.objects.filter(participants=user).filter(participants=other_user).first()
        except (User.DoesNotExist, ValueError):
            pass
            
        return None

    def _wrap_messages(self, data, request):
        from accounts.models import Profile
        from accounts.serializers import ProfileSerializer
        from .models import Message as ChatMessageModel
        
        wrapped = []
        for msg_data in data:
            try:
                # Use msg_data['id'] which is the UUID of the message
                msg = ChatMessageModel.objects.get(id=msg_data['id'])
                participants = msg.conversation.participants.all()
                receiver_user = participants.exclude(id=msg.sender.id).first()
                
                sender_profile = Profile.objects.filter(user=msg.sender).first()
                receiver_profile = Profile.objects.filter(user=receiver_user).first() if receiver_user else None
                
                wrapped.append({
                    "message": msg_data,
                    "sender": ProfileSerializer(sender_profile, context={'request': request}).data if sender_profile else None,
                    "receiver": ProfileSerializer(receiver_profile, context={'request': request}).data if receiver_profile else None,
                })
            except (ChatMessageModel.DoesNotExist, KeyError):
                continue
        return wrapped
