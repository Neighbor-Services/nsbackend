import json
import logging
from celery import shared_task
from django.core.serializers.json import DjangoJSONEncoder
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification, DeviceToken
from .serializers import NotificationSerializer
from .utils import send_apns_notification

logger = logging.getLogger(__name__)

@shared_task(name='notifications.tasks.send_notification_delivery_task')
def send_notification_delivery_task(notification_id):
    """
    Handles background delivery of notifications via WebSockets and external Push services (APNs).
    """
    try:
        notification = Notification.objects.select_related('user').get(id=notification_id)
        user = notification.user
        
        # 1. Send to WebSocket (Real-time in-app notification)
        channel_layer = get_channel_layer()
        group_name = f"user_{user.id}"
        
        # Serialize data for the websocket payload
        raw_data = NotificationSerializer(notification).data
        # Ensure UUIDs and other non-serializable objects are converted to strings
        serialized_data = json.loads(json.dumps(raw_data, cls=DjangoJSONEncoder))
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notification_message",
                "message": serialized_data
            }
        )

        # 2. Send to Native Push (iOS via APNs)
        ios_tokens = DeviceToken.objects.filter(user=user, platform='IOS', is_active=True)
        if ios_tokens.exists():
            for device_token in ios_tokens:
                try:
                    # Execute the async APNs helper synchronously within the task
                    async_to_sync(send_apns_notification)(
                        device_token.token, 
                        notification.title, 
                        notification.message, 
                        notification.data
                    )
                except Exception as e:
                    logger.error(f"Failed to deliver APNs push to token {device_token.token}: {e}")
                
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found; delivery aborted.")
    except Exception as e:
        logger.error(f"Unexpected error in send_notification_delivery_task: {e}")
