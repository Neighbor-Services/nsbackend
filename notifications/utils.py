import time
import jwt
import httpx
import json
import logging
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification, DeviceToken
from .serializers import NotificationSerializer

from django.core.cache import cache
logger = logging.getLogger(__name__)

# APNs specific logic has been removed since FCM now handles cross-platform native pushes.

def send_notification(user, title, message, notification_type, data=None, sender=None):
    if data is None:
        data = {}
        
    # 1. Save to Database
    notification = Notification.objects.create(
        user=user,
        sender=sender,
        title=title,
        message=message,
        notification_type=notification_type,
        data=data
    )
    
    # Invalidate Cache
    cache.delete(f"notifications_user_{user.id}")
    
    # 2. Enqueue Background Delivery
    # We use transaction.on_commit to ensure the task only runs after the notification
    # is successfully saved and committed to the database.
    from .tasks import send_notification_delivery_task
    from django.db import transaction
    
    def trigger_task():
        send_notification_delivery_task.delay(str(notification.id))

    transaction.on_commit(trigger_task)
