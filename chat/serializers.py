from rest_framework import serializers
from .models import Conversation, Message

class MessageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    sender_email = serializers.ReadOnlyField(source='sender.email')
    chat_room_id = serializers.SerializerMethodField()
    read = serializers.BooleanField(source='is_seen', read_only=True)
    updated_at = serializers.DateTimeField(source='created_at', read_only=True)
    receiver = serializers.SerializerMethodField()
    sender = serializers.UUIDField(source='sender.id', read_only=True)

    def get_chat_room_id(self, obj):
        # Return the original ID from context if provided, else use the UUID
        return self.context.get('original_id', str(obj.conversation.id))

    def get_receiver(self, obj):
        # Avoid a DB hit per message — derive receiver from context if available,
        # otherwise fall back to querying participants (only on direct retrieve calls).
        request = self.context.get('request')
        if request:
            # The receiver is the participant who is NOT the sender
            sender_id = str(obj.sender.id)
            user_id = str(request.user.id)
            # If sender == current user, receiver is the other party (unknown here without query)
            # The _wrap_messages layer in the view already resolves this accurately per-page;
            # this field is a lightweight fallback for single-message retrieve only.
            if sender_id != user_id:
                return user_id  # current user is the receiver
        # Fallback: query participants (only hits on direct message retrieve, not list)
        participants = obj.conversation.participants.all()
        for participant in participants:
            if participant != obj.sender:
                return str(participant.id)
        return None

    media_url = serializers.SerializerMethodField()

    def get_media_url(self, obj):
        if obj.media_url:
            return obj.media_url
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    class Meta:
        model = Message
        fields = (
            'id', 'chat_room_id', 'sender', 'receiver', 'sender_email', 'message', 'content',
            'with_image', 'is_calender', 'with_image_and_text',
            'calender_date',
            'media_url', 'image', 'file_name', 'read', 'is_seen',
            'created_at', 'updated_at'
        )
        read_only_fields = ('sender', 'created_at')

class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Conversation
        fields = '__all__'
