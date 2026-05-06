from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.db.models import F, FloatField, Q
from django.db.models.functions import ACos, Cos, Radians, Sin, Cast
import math
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_new_proposal_email_task(self, proposal_id):
    """
    Celery task to send an email to the Seeker when a new proposal is received.
    """
    try:
        from .models import Proposal
        
        proposal = Proposal.objects.select_related(
            'request', 'provider', 'request__user'
        ).get(id=proposal_id)
        
        service_request = proposal.request
        provider = proposal.provider
        seeker = service_request.user
        
        # Get names
        try:
           provider_name = provider.profile.first_name if hasattr(provider, 'profile') else provider.email
        except:
            provider_name = provider.email
            
        try:
            seeker_name = seeker.profile.first_name if hasattr(seeker, 'profile') else seeker.email
        except:
            seeker_name = seeker.email

        subject = f'New Proposal for {service_request.title}'
        context = {
            'seeker_name': seeker_name,
            'provider_name': provider_name,
            'request_title': service_request.title,
            'request_id': str(service_request.id),
            'price': proposal.price,
            'description': proposal.description
        }
        
        html_content = render_to_string('services/emails/proposal_received.html', context)
        text_content = strip_tags(html_content)

        send_mail(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [seeker.email],
            html_message=html_content,
            fail_silently=False
        )
        return f"New Proposal email sent to {seeker.email}"

    except Proposal.DoesNotExist:
        return f"Proposal {proposal_id} not found"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_proposal_approval_email_task(self, proposal_id):
    """
    Celery task to send an email to the provider when their proposal is approved.
    """
    try:
        from .models import Proposal
        
        proposal = Proposal.objects.select_related(
            'request', 'provider', 'request__user'
        ).get(id=proposal_id)
        
        service_request = proposal.request
        provider = proposal.provider
        seeker = service_request.user
        
        # Get names
        try:
           provider_name = provider.profile.first_name if hasattr(provider, 'profile') else provider.email
        except:
            provider_name = provider.email
            
        try:
            seeker_name = seeker.profile.first_name if hasattr(seeker, 'profile') else seeker.email
        except:
            seeker_name = seeker.email
            
        subject = f'🎉 Proposal Accepted: {service_request.title}'
        
        context = {
            'provider_name': provider_name,
            'seeker_name': seeker_name,
            'seeker_email': seeker.email,
            'request_title': service_request.title,
            'price': service_request.price,
            'scheduled_time': service_request.scheduled_time.strftime('%B %d, %Y at %I:%M %p') if service_request.scheduled_time else None
        }

        html_content = render_to_string('services/emails/proposal_approved.html', context)
        text_content = strip_tags(html_content)
        
        send_mail(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [provider.email],
            html_message=html_content,
            fail_silently=False
        )
        
        return f"Approval email sent successfully to {provider.email}"
        
    except Proposal.DoesNotExist:
        return f"Proposal {proposal_id} not found"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_direct_request_email_task(self, request_id):
    """
    Celery task to send an email to the provider when a direct service request is received.
    """
    try:
        print(f"DEBUG: Starting send_direct_request_email_task for request_id: {request_id}")
        from .models import ServiceRequest
        
        service_request = ServiceRequest.objects.select_related(
            'user', 'target_provider'
        ).get(id=request_id)
        
        if not service_request.target_provider:
            return f"Service Request {request_id} has no target provider"
            
        provider = service_request.target_provider
        seeker = service_request.user
        
        # Get names
        try:
           provider_name = provider.profile.first_name if hasattr(provider, 'profile') else provider.email
        except:
            provider_name = provider.email
            
        try:
            seeker_name = seeker.profile.first_name if hasattr(seeker, 'profile') else seeker.email
        except:
            seeker_name = seeker.email
            
        subject = f'📬 New Direct Service Request: {service_request.title}'
        
        context = {
            'provider_name': provider_name,
            'seeker_name': seeker_name,
            'request_title': service_request.title,
            'price': service_request.price,
            'scheduled_time': service_request.scheduled_time.strftime('%B %d, %Y at %I:%M %p') if service_request.scheduled_time else None,
            'description': service_request.description,
            'request_id': str(service_request.id)
        }

        html_content = render_to_string('services/emails/direct_request.html', context)
        text_content = strip_tags(html_content)
        
        send_mail(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [provider.email],
            html_message=html_content,
            fail_silently=False
        )
        
        return f"Direct Request email sent successfully to {provider.email}"
        
    except ServiceRequest.DoesNotExist:
        return f"Service Request {request_id} not found"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def notify_nearby_providers_task(self, request_id):
    """
    Celery task to notify verified providers within 25km of a new service request.
    """
    try:
        from .models import ServiceRequest
        from accounts.models import Profile
        from notifications.utils import send_notification
        
        service_request = ServiceRequest.objects.select_related('user').get(id=request_id)
        
        # Skip if no location
        if not service_request.latitude or not service_request.longitude:
            return f"Service Request {request_id} has no location data"

        lat = float(service_request.latitude)
        lng = float(service_request.longitude)
        lat_rad = math.radians(lat)
        lng_rad = math.radians(lng)

        # 1. Find verified providers within 25km using Haversine formula
        # We use the same formula as in the ViewSet for consistency
        nearby_providers = Profile.objects.filter(
            user_type='PROVIDER',
            is_identity_verified=True,
            latitude__isnull=False,
            longitude__isnull=False
        ).annotate(
            distance=6371 * ACos(
                Sin(lat_rad) * Sin(Radians(Cast(F('latitude'), FloatField()))) +
                Cos(lat_rad) * Cos(Radians(Cast(F('latitude'), FloatField()))) *
                Cos(Radians(Cast(F('longitude'), FloatField())) - lng_rad),
                output_field=FloatField(),
            )
        ).filter(distance__lte=25.0).select_related('user')

        count = 0
        seeker_name = service_request.user.profile.first_name if hasattr(service_request.user, 'profile') and service_request.user.profile.first_name else service_request.user.email
        
        for profile in nearby_providers:
            # Avoid notifying the seeker if they happen to be a provider too
            if profile.user == service_request.user:
                continue

            # A. Send Push Notification
            try:
                send_notification(
                    user=profile.user,
                    title="New Service Request Nearby",
                    message=f"A new request for '{service_request.title}' was posted {profile.distance:.1f}km away.",
                    notification_type="BROADCAST_REQUEST",
                    data={"request_id": str(service_request.id)}
                )
            except Exception as e:
                logger.error(f"Failed to send push notification to {profile.user.email}: {e}")

            # B. Send Email
            try:
                context = {
                    'provider_name': profile.first_name or profile.user.email,
                    'seeker_name': seeker_name,
                    'request_title': service_request.title,
                    'distance': profile.distance,
                    'request_id': str(service_request.id),
                    'description': service_request.description,
                    'scheduled_time': service_request.scheduled_time.strftime('%B %d, %Y at %I:%M %p') if service_request.scheduled_time else None
                }
                
                html_content = render_to_string('services/emails/broadcast_request.html', context)
                text_content = strip_tags(html_content)
                
                send_mail(
                    f"📍 New Service Request Nearby: {service_request.title}",
                    text_content,
                    settings.DEFAULT_FROM_EMAIL,
                    [profile.user.email],
                    html_message=html_content,
                    fail_silently=True
                )
            except Exception as e:
                logger.error(f"Failed to send broadcast email to {profile.user.email}: {e}")
            
            count += 1

        return f"Broadcasted request {request_id} to {count} nearby providers"

    except ServiceRequest.DoesNotExist:
        return f"Service Request {request_id} not found"
    except Exception as exc:
        logger.error(f"Error in notify_nearby_providers_task: {exc}")
        raise self.retry(exc=exc, countdown=60)
