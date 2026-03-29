from django.db import models
from django.conf import settings
import uuid
from encrypted_model_fields.fields import EncryptedTextField

class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Conversation {self.id}"

class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    content = EncryptedTextField()
    message = models.TextField(blank=True, null=True)  # Alias for content for frontend compatibility
    with_image = models.BooleanField(default=False)
    is_calender = models.BooleanField(default=False)
    with_image_and_text = models.BooleanField(default=False)
    calender_date = models.DateTimeField(null=True, blank=True)
    media_url = models.URLField(blank=True, null=True)
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    is_seen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"From {self.sender.email} at {self.created_at}"
