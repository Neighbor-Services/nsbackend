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
    
    # 2. Enqueue Background Delivery
    # We use transaction.on_commit to ensure the task only runs after the notification
    # is successfully saved and committed to the database.
    from .tasks import send_notification_delivery_task
    from django.db import transaction
    
    def trigger_task():
        send_notification_delivery_task.delay(str(notification.id))

    transaction.on_commit(trigger_task)
