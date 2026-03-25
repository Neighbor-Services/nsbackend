from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Profile, ServicePackage, PortfolioItem, LegalDocument
from services.ai_matching import EmbeddingService
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Profile)
def update_profile_embedding(sender, instance, **kwargs):
    # Only generate if bio/about (which is in About model?) or fields change.
    # Profile has basic info. 'About' has description.
    # Wait, simple Profile doesn't have a 'bio'. 'About' model does.
    # I should check About model for embedding?
    # Profile has: first_name, last_name, service (title).
    # About has: description, specification.
    # I should attach embedding to 'About' or 'Profile'?
    # Plan said 'Profile.bio' but Profile doesn't have bio. 'About' has 'description'.
    # I added 'bio_embedding' to 'Profile'.
    # I should aggregate text from Profile and About?
    # Or just listen to 'About' save and update Profile?
    pass

@receiver(post_save, sender=ServicePackage)
def update_service_package_embedding(sender, instance, created, **kwargs):
    if instance.description:
        # Check if description changed? (Need pre_save for that, or just overwrite)
        # Using post_save, we just overwrite.
        embedding = EmbeddingService.get_embedding(instance.description)
        if embedding:
            ServicePackage.objects.filter(pk=instance.pk).update(description_embedding=embedding)
@receiver(post_save, sender=PortfolioItem)
def trigger_portfolio_ai_analysis(sender, instance, created, **kwargs):
    if created and instance.image:
        from .tasks import analyze_portfolio_image_task
        analyze_portfolio_image_task.delay(instance.id)

@receiver([post_save, post_delete], sender=LegalDocument)
def invalidate_legal_docs_cache(sender, instance, **kwargs):
    """Clear cache for both TERMS and PRIVACY when any document is changed."""
    cache.delete("legal_docs_TERMS")
    cache.delete("legal_docs_PRIVACY")
    logger.info(f"Invalidated legal documents cache due to change in {instance}")
