from celery import shared_task
from chat.models import Message
from interactions.models import Review
from .ai_utils import analyze_content_with_ai
import logging

logger = logging.getLogger(__name__)

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
            message.content = result.get('masked_content') # Update both alias and encrypted field
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
            # For reviews, we might just flag them for admin review instead of masking?
            # For now, let's mask inappropriate content.
            review.comment = result.get('masked_content')
            review.save()
            logger.info(f"Review {review_id} moderated and masked.")
            
    except Review.DoesNotExist:
        logger.error(f"Review {review_id} not found for moderation.")
    except Exception as e:
        logger.error(f"Error in moderate_review_task: {str(e)}")
