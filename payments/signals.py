from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Subscription

@receiver(post_save, sender=Subscription)
def update_profile_tier_on_save(sender, instance, **kwargs):
    """Update profile tier when subscription is saved/updated"""
    try:
        profile = instance.user.profile
        if instance.is_active and instance.plan:
            profile.subscription_tier = instance.plan.tier
        else:
            profile.subscription_tier = 'NONE'
            profile.catalog_services.clear()
        profile.save()
    except Exception as e:
        print(f"Error updating profile tier on save: {e}")

@receiver(post_delete, sender=Subscription)
def update_profile_tier_on_delete(sender, instance, **kwargs):
    """Reset profile tier to NONE and clear catalog services when subscription is deleted"""
    try:
        profile = instance.user.profile
        profile.subscription_tier = 'NONE'
        profile.catalog_services.clear()
        profile.save()
    except Exception as e:
        print(f"Error updating profile tier on delete: {e}")
