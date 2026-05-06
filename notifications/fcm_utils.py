import logging
import os

logger = logging.getLogger(__name__)

# Firebase Admin SDK is initialized lazily, once per process
_firebase_app = None


def _get_firebase_app():
    """Lazily initialize and return the Firebase Admin SDK app."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials
        from django.conf import settings

        key_path = getattr(settings, 'FCM_SERVICE_ACCOUNT_KEY_PATH', None)
        if not key_path or not os.path.exists(key_path):
            logger.error(
                "FCM_SERVICE_ACCOUNT_KEY_PATH is not configured or the file does not exist. "
                "Download a service account key from Firebase Console → Project Settings → "
                "Service Accounts → Generate new private key, and set the path in your .env file."
            )
            return None

        cred = credentials.Certificate(key_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully.")
        return _firebase_app

    except ImportError:
        logger.error(
            "firebase-admin is not installed. Run: pip install firebase-admin"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return None


def send_fcm_notification(token: str, title: str, body: str, data: dict = None) -> bool:
    """
    Sends an FCM push notification to an Android device via the HTTP v1 API.

    Args:
        token: The FCM registration token of the target device.
        title: Notification title.
        body:  Notification body.
        data:  Optional dict of extra string key/value pairs sent as data payload.

    Returns:
        True on success, False on failure.
    """
    if data is None:
        data = {}

    app = _get_firebase_app()
    if app is None:
        return False

    try:
        from firebase_admin import messaging
        from .models import DeviceToken

        # Ensure all values in data are strings (FCM requirement)
        str_data = {k: str(v) for k, v in data.items() if v is not None}

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=str_data,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    channel_id='high_importance_channel',
                    sound='default',
                    priority='high',
                    default_vibrate_timings=True,
                ),
            ),
            apns=messaging.APNSConfig(
                headers={
                    'apns-priority': '10',          # 10 = immediate delivery
                    'apns-push-type': 'alert',
                },
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=title,
                            body=body,
                        ),
                        sound='default',
                        badge=1,
                        content_available=True,
                    ),
                ),
            ),
            token=token,
        )

        response = messaging.send(message)
        logger.info(f"Successfully sent FCM notification. Message ID: {response}")
        return True

    except Exception as e:
        error_str = str(e)
        # Handle stale / invalid tokens
        if 'UNREGISTERED' in error_str or 'registration-token-not-registered' in error_str:
            logger.warning(
                f"FCM token {token} is no longer registered. Deactivating."
            )
            try:
                from .models import DeviceToken
                DeviceToken.objects.filter(token=token).update(is_active=False)
            except Exception as db_err:
                logger.error(f"Failed to deactivate stale FCM token: {db_err}")
        else:
            logger.error(f"Failed to send FCM notification to token {token}: {e}")
        return False
