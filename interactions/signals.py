from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Review
from moderation.tasks import moderate_review_task

@receiver(post_save, sender=Review)
def trigger_review_moderation(sender, instance, created, **kwargs):
    if created:
        # Trigger the moderation task
        moderate_review_task.delay(str(instance.id))
