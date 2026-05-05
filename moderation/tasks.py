import logging

from celery import shared_task
from django.utils import timezone

from chat.models import Message
from interactions.models import Review
from .ai_utils import analyze_content_with_ai

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Existing moderation tasks (unchanged)
# ---------------------------------------------------------------------------

@shared_task
def moderate_message_task(message_id):
    try:
        message = Message.objects.get(id=message_id)
        # Avoid re-moderating
        if "[REDACTED]" in (message.message or ""):
            return

        result = analyze_content_with_ai(message.message or "", resource_type="message")

        if result.get('should_mask'):
            message.message = result.get('masked_content')
            message.content = result.get('masked_content')  # Update both alias and encrypted field
            message.save()
            logger.info(f"Message {message_id} moderated and masked.")

    except Message.DoesNotExist:
        logger.error(f"Message {message_id} not found for moderation.")
    except Exception as e:
        logger.error(f"Error in moderate_message_task: {str(e)}")


@shared_task
def moderate_review_task(review_id):
    try:
        review = Review.objects.get(id=review_id)
        result = analyze_content_with_ai(review.comment or "", resource_type="review")

        if not result.get('safe'):
            review.comment = result.get('masked_content')
            review.save()
            logger.info(f"Review {review_id} moderated and masked.")

    except Review.DoesNotExist:
        logger.error(f"Review {review_id} not found for moderation.")
    except Exception as e:
        logger.error(f"Error in moderate_review_task: {str(e)}")


# ---------------------------------------------------------------------------
# Checkr background check sync tasks
# ---------------------------------------------------------------------------

MAX_SYNC_ATTEMPTS = 10  # Stop polling after this many failed attempts


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_checkr_report_task(self, background_check_id: str):
    """
    Celery task to manually sync a single BackgroundCheck from Checkr.

    Used as a fallback if the webhook hasn't fired within the expected window.
    Retries up to 3 times with a 5-minute delay between attempts.
    """
    from .models import BackgroundCheck
    from . import checkr_client
    from .checkr_client import CheckrAPIError
    from .views import _apply_report_to_background_check

    try:
        bc = BackgroundCheck.objects.get(id=background_check_id)
    except BackgroundCheck.DoesNotExist:
        logger.error("sync_checkr_report_task: BackgroundCheck %s not found.", background_check_id)
        return

    if bc.is_terminal:
        logger.info(
            "sync_checkr_report_task: BackgroundCheck %s is already terminal (%s), skipping.",
            bc.id, bc.status,
        )
        return

    if not bc.checkr_report_id:
        logger.info(
            "sync_checkr_report_task: BackgroundCheck %s has no report ID yet "
            "(provider may not have completed invitation form).",
            bc.id,
        )
        return

    if bc.sync_attempt_count >= MAX_SYNC_ATTEMPTS:
        logger.warning(
            "sync_checkr_report_task: BackgroundCheck %s reached max sync attempts (%s). Stopping.",
            bc.id, MAX_SYNC_ATTEMPTS,
        )
        return

    try:
        report = checkr_client.get_report(bc.checkr_report_id)
        _apply_report_to_background_check(bc, report)
        logger.info("sync_checkr_report_task: BackgroundCheck %s synced successfully.", bc.id)
    except CheckrAPIError as exc:
        logger.error("sync_checkr_report_task: Checkr API error for %s: %s", bc.id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "sync_checkr_report_task: Max retries exceeded for BackgroundCheck %s.", bc.id
            )


@shared_task
def sync_pending_checkr_reports():
    """
    Periodic Celery Beat task: finds all PENDING background checks that
    haven't been updated in >1 hour and re-queues them for sync.

    Scheduled every hour via CELERY_BEAT_SCHEDULE.
    """
    from .models import BackgroundCheck

    one_hour_ago = timezone.now() - timezone.timedelta(hours=1)

    stale_checks = BackgroundCheck.objects.filter(
        status=BackgroundCheck.STATUS_PENDING,
        checkr_report_id__isnull=False,  # Only if we actually have a report ID
        updated_at__lt=one_hour_ago,
        sync_attempt_count__lt=MAX_SYNC_ATTEMPTS,
    )

    count = stale_checks.count()
    if count == 0:
        logger.info("sync_pending_checkr_reports: No stale checks found.")
        return

    logger.info("sync_pending_checkr_reports: Queuing %s stale background checks.", count)

    for bc in stale_checks:
        sync_checkr_report_task.delay(str(bc.id))

    return f"Queued {count} checks for sync."
