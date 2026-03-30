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

logger = logging.getLogger(__name__)

def _generate_apns_jwt():
    """Generates a JWT for APNs authentication."""
    if not settings.APNS_KEY_ID or not settings.APNS_TEAM_ID:
        logger.error("APNS configuration missing Key ID or Team ID")
        return None

    try:
        with open(settings.APNS_KEY_PATH, 'r') as f:
            secret = f.read()
    except Exception as e:
        logger.error(f"Failed to read APNS key file: {e}")
        return None

    token = jwt.encode(
        {
            'iss': settings.APNS_TEAM_ID,
            'iat': time.time()
        },
        secret,
        algorithm='ES256',
        headers={
            'alg': 'ES256',
            'kid': settings.APNS_KEY_ID
        }
    )
    return token

async def send_apns_notification(token, title, body, data=None):
    """Sends a push notification directly to Apple APNs using HTTP/2."""
    if data is None:
        data = {}

    auth_token = _generate_apns_jwt()
    if not auth_token:
        return

    # Determine endpoint based on sandbox setting
    base_url = "https://api.development.push.apple.com" if settings.APNS_USE_SANDBOX else "https://api.push.apple.com"
    url = f"{base_url}/3/device/{token}"

    headers = {
        'apns-topic': settings.APNS_BUNDLE_ID,
        'authorization': f'bearer {auth_token}',
        'apns-priority': '10',
        'apns-push-type': 'alert'
    }

    payload = {
        'aps': {
            'alert': {
                'title': title,
                'body': body
            },
            'sound': 'default',
            'badge': 1
        }
    }
    # Add extra data if any
    if data:
        payload.update(data)

    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                logger.info(f"Successfully sent APNs notification to {token}")
            elif response.status_code == 410:
                # Token is no longer valid (app uninstalled)
                logger.warning(f"APNs token {token} is no longer valid. Deactivating.")
                DeviceToken.objects.filter(token=token).update(is_active=False)
            else:
                logger.error(f"Failed to send APNs notification: {response.text}")
        except Exception as e:
            logger.error(f"Error during APNs request: {e}")

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

    # 3. Send to Native Push (iOS via APNs)
    ios_tokens = DeviceToken.objects.filter(user=user, platform='IOS', is_active=True)
    for device_token in ios_tokens:
        # We run this in a fire-and-forget manner or we can use a worker.
        # Since we use async_to_sync above, we'll do the same for the APNs call
        # for immediate execution, or ideally this should be a Celery task.
        try:
            async_to_sync(send_apns_notification)(
                device_token.token, 
                title, 
                message, 
                data
            )
        except Exception as e:
            logger.error(f"Could not trigger APNs for {user.email}: {e}")
