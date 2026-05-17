from celery import shared_task
import logging
from .models import PortfolioItem, User
from .ai_utils import analyze_portfolio_image
import os
from .utils import send_otp_email

logger = logging.getLogger(__name__)

@shared_task
def analyze_portfolio_image_task(item_id):
    """
    Celery task to analyze portfolio image and update tags/description.
    """
    try:
        item = PortfolioItem.objects.get(id=item_id)
        if not item.image:
            return

        # Ensure image path is absolute
        image_path = item.image.path
        if not os.path.exists(image_path):
            logger.error(f"Image not found at path: {image_path}")
            return

        result = analyze_portfolio_image(image_path)
        
        if result['tags']:
            item.tags = result['tags']
        
        # Only update description if it was empty
        if not item.description and result['description']:
            item.description = result['description'][:255]
            
        item.save()
        logger.info(f"AI Analysis completed for PortfolioItem {item_id}")

    except PortfolioItem.DoesNotExist:
        logger.error(f"PortfolioItem {item_id} does not exist.")
    except Exception as e:
        logger.error(f"Error in analyze_portfolio_image_task: {str(e)}")

@shared_task
def send_otp_email_task(user_id, otp):
    """
    Celery task to asynchronously send an OTP verification email.
    """
    try:
        user = User.objects.get(id=user_id)
        send_otp_email(user, otp)
        logger.info(f"OTP email sent asynchronously to User {user_id}")
    except User.DoesNotExist:
        logger.error(f"Failed to send OTP: User {user_id} does not exist.")
    except Exception as e:
        logger.error(f"Error sending OTP email via Celery: {str(e)}")
