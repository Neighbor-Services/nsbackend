from rest_framework import serializers
from .models import Notification, DeviceToken
from accounts.serializers import SimpleProfileSerializer

class NotificationSerializer(serializers.ModelSerializer):
    sender_profile = SimpleProfileSerializer(source='sender.profile', read_only=True)

    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('created_at',)

class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ('id', 'token', 'platform', 'device_id', 'is_active', 'created_at')
        read_only_fields = ('id', 'created_at')
