from django.db import models
from django.conf import settings
import uuid

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('PROPOSAL', 'New Proposal'),
        ('APPOINTMENT', 'Appointment Update'),
        ('MESSAGE', 'New Message'),
        ('SYSTEM', 'System Alert'),
        ('DIRECT_REQUEST', 'Direct Service Request'),
        
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True) # For extra payload (e.g. request_id)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notification_type} for {self.user.email}"

class DeviceToken(models.Model):
    PLATFORM_CHOICES = (
        ('IOS', 'iOS'),
        ('ANDROID', 'Android'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    device_id = models.CharField(max_length=255, blank=True, null=True) # Unique ID from the physical device
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['token']),
        ]

    def __str__(self):
        return f"{self.platform} token for {self.user.email}"
