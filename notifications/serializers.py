from rest_framework import serializers
from .models import Notification
from accounts.serializers import SimpleProfileSerializer

class NotificationSerializer(serializers.ModelSerializer):
    sender_profile = SimpleProfileSerializer(source='sender.profile', read_only=True)

    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('user', 'created_at')
