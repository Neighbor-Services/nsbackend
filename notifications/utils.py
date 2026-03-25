from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification
from .serializers import NotificationSerializer

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
    
    # 2. Send to WebSocket
    channel_layer = get_channel_layer()
    group_name = f"user_{user.id}"
    
    # Serialize the notification data for the websocket
    serialized_data = NotificationSerializer(notification).data
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "notification_message",
            "message": serialized_data
        }
    )
