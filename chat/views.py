from rest_framework import viewsets, permissions
from rest_framework.response import Response
from .models import Conversation, Message, ChatBlock
from .serializers import ConversationSerializer, MessageSerializer, ChatBlockSerializer

class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        from django.db.models import Prefetch, OuterRef, Subquery
        # Only prefetch the LAST message per conversation for the list view.
        # Loading all messages here would pull thousands of rows into memory
        # just to show conversation previews.
        last_msg_ids = Message.objects.filter(
            conversation=OuterRef('pk')
        ).order_by('-created_at').values('id')[:1]

        # Get conversation IDs where the current user is involved in a block
        # (either as blocker or blocked)
        blocked_conv_ids = ChatBlock.objects.filter(
            conversation__participants=self.request.user
        ).filter(
            blocker=self.request.user
        ).values_list('conversation_id', flat=True)

        return Conversation.objects.filter(
            participants=self.request.user
        ).exclude(
            id__in=blocked_conv_ids
        ).prefetch_related(
            'participants',
            Prefetch(
                'messages',
                queryset=Message.objects.filter(
                    id__in=Subquery(last_msg_ids)
                ).select_related('sender'),
                to_attr='last_messages',
            ),
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

    @action(detail=False, methods=['post'], url_path='block_chat')
    def block_chat(self, request):
        """Block a user in a specific conversation."""
        conversation_id = request.data.get('conversation_id')
        user_id = request.data.get('user_id')

        if not conversation_id or not user_id:
            return Response(
                {"error": "conversation_id and user_id are required"}, status=400
            )

        try:
            conversation = Conversation.objects.get(
                id=conversation_id, participants=request.user
            )
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found"}, status=404)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            blocked_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        # Verify the blocked user is actually a participant
        if not conversation.participants.filter(id=blocked_user.id).exists():
            return Response(
                {"error": "User is not a participant in this conversation"}, status=400
            )

        block, created = ChatBlock.objects.get_or_create(
            blocker=request.user,
            blocked=blocked_user,
            conversation=conversation,
        )

        if not created:
            return Response({"status": "already_blocked"})

        # Send a block_status event via WebSocket so the other user gets notified in real-time
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            room_group_name = f'chat_{conversation.id}'
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chat_status',
                    'status_data': {
                        'type': 'block_status',
                        'blocker_id': str(request.user.id),
                        'blocked_id': str(blocked_user.id),
                        'is_blocked': True,
                    }
                }
            )
        except Exception:
            pass  # Don't fail the block if WS notification fails

        serializer = ChatBlockSerializer(block)
        return Response({"status": "blocked", "block": serializer.data}, status=201)

    @action(detail=False, methods=['post'], url_path='unblock_chat')
    def unblock_chat(self, request):
        """Unblock a user in a specific conversation."""
        conversation_id = request.data.get('conversation_id')
        user_id = request.data.get('user_id')

        if not conversation_id or not user_id:
            return Response(
                {"error": "conversation_id and user_id are required"}, status=400
            )

        deleted_count, _ = ChatBlock.objects.filter(
            blocker=request.user,
            blocked_id=user_id,
            conversation_id=conversation_id,
        ).delete()

        if deleted_count == 0:
            return Response({"status": "not_blocked"})

        # Send unblock notification via WebSocket
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            room_group_name = f'chat_{conversation_id}'
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chat_status',
                    'status_data': {
                        'type': 'block_status',
                        'blocker_id': str(request.user.id),
                        'blocked_id': str(user_id),
                        'is_blocked': False,
                    }
                }
            )
        except Exception:
            pass

        return Response({"status": "unblocked"})

    @action(detail=False, methods=['get'], url_path='blocked_users')
    def blocked_users(self, request):
        """List all users blocked by the current user."""
        blocks = ChatBlock.objects.filter(
            blocker=request.user
        ).select_related('blocked', 'conversation')
        serializer = ChatBlockSerializer(blocks, many=True)
        return Response(serializer.data)

    def _wrap_conversations(self, data, request):
        from accounts.models import Profile
        from accounts.serializers import ProfileSerializer

        me_id = str(request.user.id)

        # Collect ALL participant IDs across all conversations in one pass
        all_participant_ids = set()
        for conv_data in data:
            for pid in conv_data['participants']:
                all_participant_ids.add(str(pid))

        # ONE bulk query for all needed profiles instead of 2 per conversation
        profiles_qs = Profile.objects.filter(
            user_id__in=all_participant_ids
        ).select_related('user')
        profiles_map = {str(p.user_id): p for p in profiles_qs}

        # Bulk-fetch block status for all conversations in one query
        conv_ids = [conv_data['id'] for conv_data in data]
        blocked_set = set(
            ChatBlock.objects.filter(
                conversation_id__in=conv_ids,
            ).filter(
                blocker=request.user
            ).values_list('conversation_id', flat=True)
        )
        # Also check if the current user has been blocked by the other party
        blocked_by_set = set(
            ChatBlock.objects.filter(
                conversation_id__in=conv_ids,
                blocked=request.user,
            ).values_list('conversation_id', flat=True)
        )

        wrapped = []
        for conv_data in data:
            conv_id = conv_data['id']
            participants_ids = [str(pid) for pid in conv_data['participants']]
            other_id = next((pid for pid in participants_ids if pid != me_id), None)

            me_profile = profiles_map.get(me_id)
            other_profile = profiles_map.get(other_id) if other_id else None

            # Use last_messages (single prefetched msg) instead of all messages
            messages_list = conv_data.get('last_messages', conv_data.get('messages', []))
            unread_count = sum(
                1 for msg in messages_list
                if not msg.get('is_seen', False) and str(msg.get('sender')) != me_id
            )

            # Determine block status
            is_blocked_by_me = str(conv_id) in {str(cid) for cid in blocked_set}
            is_blocked_by_other = str(conv_id) in {str(cid) for cid in blocked_by_set}

            chat_data = {
                "id": conv_id,
                "chat_room": conv_id,
                "user1": me_id,
                "user2": other_id,
                "unread_count": unread_count,
                "created_at": conv_data.get('created_at'),
                "updated_at": conv_data.get('updated_at'),
                "last_message": messages_list[-1] if messages_list else None,
                "is_blocked": is_blocked_by_me or is_blocked_by_other,
                "is_blocked_by_me": is_blocked_by_me,
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
                
        # Filter by after query param for incremental sync
        after_param = self.request.query_params.get('after')
        if after_param:
            queryset = queryset.filter(created_at__gt=after_param)

        # Filter by before query param for loading older messages
        before_param = self.request.query_params.get('before')
        if before_param:
            # We want the 10 messages JUST BEFORE this timestamp, 
            # so we sort descending, take 10, then we'll reverse them 
            # at the end of this method to maintain chronological order.
            queryset = queryset.filter(created_at__lt=before_param).order_by('-created_at')[:10]
            # Since we've already sliced it ([:10]), we shouldn't paginate again
            serializer = self.get_serializer(reversed(queryset), many=True, context={'original_id': conversation_param, 'request': request})
            wrapped_data = self._wrap_messages(serializer.data, request)
            return Response(wrapped_data)
            
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
        
        try:
            val = uuid.UUID(conversation_id, version=4)
            conv = Conversation.objects.filter(id=val, participants=user).first()
            if conv:
                return conv
        except ValueError:
            pass

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
        
        try:
            other_user = User.objects.get(id=conversation_id)
            return Conversation.objects.filter(participants=user).filter(participants=other_user).first()
        except (User.DoesNotExist, ValueError):
            pass
            
        return None

    def _wrap_messages(self, data, request):
        from accounts.models import Profile
        from accounts.serializers import ProfileSerializer

        if not data:
            return []

        # Collect all sender IDs in one pass, then bulk-fetch profiles
        sender_ids = {str(msg['sender']) for msg in data if msg.get('sender')}
        profiles_qs = Profile.objects.filter(
            user_id__in=sender_ids
        ).select_related('user')
        profiles_map = {str(p.user_id): p for p in profiles_qs}

        # For receiver we need participants — fetch the conversation once
        # (all messages in one list view belong to the same conversation)
        receiver_profile = None
        if data:
            try:
                from .models import Message as ChatMessageModel
                first_msg = ChatMessageModel.objects.select_related('conversation').get(
                    id=data[0]['id']
                )
                me_id = str(request.user.id)
                receiver_user = first_msg.conversation.participants.exclude(
                    id=request.user.id
                ).first()
                if receiver_user:
                    receiver_profile = Profile.objects.filter(
                        user=receiver_user
                    ).select_related('user').first()
            except Exception:
                pass

        serialized_receiver = (
            ProfileSerializer(receiver_profile, context={'request': request}).data
            if receiver_profile else None
        )

        wrapped = []
        for msg_data in data:
            sender_profile = profiles_map.get(str(msg_data.get('sender')))
            wrapped.append({
                "message": msg_data,
                "sender": ProfileSerializer(sender_profile, context={'request': request}).data if sender_profile else None,
                "receiver": serialized_receiver,
            })
        return wrapped
