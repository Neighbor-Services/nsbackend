import logging
from .models import AuditLog

logger = logging.getLogger(__name__)

def log_audit_action(user, action, resource_type, resource_id=None, details=None, request=None):
    """
    Safely creates an AuditLog entry.
    """
    try:
        ip_address = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

        # Use None if user is not authenticated or not a valid User instance
        actor = user if user and getattr(user, 'is_authenticated', False) else None

        AuditLog.objects.create(
            user=actor,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details or {},
            ip_address=ip_address
        )
    except Exception as e:
        logger.error(f"Failed to create audit log for {action}: {e}")
