from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message
from moderation.tasks import moderate_message_task

@receiver(post_save, sender=Message)
def trigger_message_moderation(sender, instance, created, **kwargs):
    if created:
        # Trigger the moderation task
        moderate_message_task.delay(str(instance.id))
