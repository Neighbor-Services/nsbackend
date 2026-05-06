import logging
from celery import shared_task
from .models import Notification, DeviceToken
from .fcm_utils import send_fcm_notification

logger = logging.getLogger(__name__)

@shared_task(name='notifications.tasks.send_notification_delivery_task', bind=True, max_retries=3, default_retry_delay=30)
def send_notification_delivery_task(self, notification_id):
    """
    Handles background delivery of notifications via:
      1. FCM — native push for both iOS and Android devices (handles both foreground and background natively)
    """
    try:
        notification = Notification.objects.select_related('user').get(id=notification_id)
        user = notification.user



        # Build shared extra data payload
        extra_data = dict(notification.data) if notification.data else {}
        extra_data.update({
            'notification_id': str(notification.id),
            'notification_type': notification.notification_type,
        })

        # ── 2. FCM (Native push for all platforms) ────────────────────────────
        device_tokens = DeviceToken.objects.filter(user=user, is_active=True)
        for device_token in device_tokens:
            try:
                send_fcm_notification(
                    device_token.token,
                    notification.title,
                    notification.message,
                    extra_data,
                )
            except Exception as e:
                logger.error(f"FCM delivery failed for token {device_token.token} ({device_token.platform}): {e}")

    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found; delivery aborted.")
    except Exception as exc:
        logger.error(f"Unexpected error in send_notification_delivery_task: {exc}")
        raise self.retry(exc=exc)

