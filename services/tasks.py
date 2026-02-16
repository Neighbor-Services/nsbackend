from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


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

