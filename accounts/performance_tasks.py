from celery import shared_task
from django.db.models import Avg, Count, F, ExpressionWrapper, DurationField
from django.utils import timezone
from datetime import timedelta
from .models import Profile, PerformanceBadge
from interactions.models import Appointment, Review
from chat.models import Message, Conversation
from django.contrib.auth import get_user_model

User = get_user_model()

@shared_task
def calculate_provider_metrics_task():
    thirty_days_ago = timezone.now() - timedelta(days=30)
    providers = Profile.objects.filter(user_type='PROVIDER')

    for profile in providers:
        user = profile.user
        
        # 1. Highly Reliable
        # Criteria: Completion rate > 95% + 0 cancellations in 30 days + at least 5 appointments
        appointments_last_30 = Appointment.objects.filter(
            provider=user, 
            created_at__gte=thirty_days_ago
        )
        total_appt = appointments_last_30.count()
        completed_appt = appointments_last_30.filter(status='COMPLETED').count()
        cancelled_appt = appointments_last_30.filter(status='CANCELLED').count()

        if total_appt >= 5:
            completion_rate = (completed_appt / total_appt) * 100
            if completion_rate >= 95 and cancelled_appt == 0:
                _award_badge(profile, "Highly Reliable", "shield", "Maintains an exceptional appointment completion rate.")
            else:
                _remove_badge(profile, "Highly Reliable")
        
        # 2. Top 1%
        # Criteria: Rating > 4.8 + top 1% by volume in category
        if profile.average_rating >= 4.8 and profile.total_reviews >= 10:
            category = profile.catalog_services.first()
            if category:
                category_providers = Profile.objects.filter(catalog_services=category).order_by('total_reviews')
                count = category_providers.count()
                if count > 10:
                    top_threshold = int(count * 0.01) or 1
                    top_providers = category_providers.reverse()[:top_threshold]
                    if profile in top_providers:
                        _award_badge(profile, "Top 1%", "star", f"Ranked in the top 1% of {category.name} providers by review volume.")
                    else:
                        _remove_badge(profile, "Top 1%")
        
        # 3. Speed King
        # Criteria: Avg response time to seeker messages < 30 mins (mock/simple logic for now)
        # We'll check the first response in each unique conversation in last 30 days
        # This is computationally expensive, so we'll do a simplified check for this iteration
        # _check_speed_king(profile)

def _award_badge(profile, name, icon, description):
    PerformanceBadge.objects.get_or_create(
        profile=profile,
        name=name,
        defaults={'icon_type': icon, 'description': description}
    )

def _remove_badge(profile, name):
    PerformanceBadge.objects.filter(profile=profile, name=name).delete()
