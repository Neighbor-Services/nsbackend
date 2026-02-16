from django.core.mail import EmailMessage
from django.conf import settings


def send_proposal_approval_email(proposal):
    """
    Sends an email to the provider when their proposal is approved by the seeker.
    """
    service_request = proposal.request
    provider = proposal.provider
    seeker = service_request.user
    
    # Get provider's profile for name
    provider_name = "Provider"
    try:
        if hasattr(provider, 'profile') and provider.profile:
            provider_name = provider.profile.first_name or provider.email
    except:
        provider_name = provider.email
    
    # Get seeker's profile for name
    seeker_name = seeker.email
    try:
        if hasattr(seeker, 'profile') and seeker.profile:
            seeker_name = f"{seeker.profile.first_name} {seeker.profile.last_name}".strip() or seeker.email
    except:
        pass
    
    subject = f'🎉 Your Proposal Has Been Accepted!'
    
    scheduled_info = ""
    if service_request.scheduled_time:
        scheduled_info = f"\nScheduled Time: {service_request.scheduled_time.strftime('%B %d, %Y at %I:%M %p')}"
    
    body = f"""Hello {provider_name},

Great news! Your proposal has been accepted by {seeker_name}.

Service Request Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: {service_request.title}
Description: {service_request.description}{scheduled_info}
Budget: ${service_request.price}

Client Contact:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: {seeker_name}
Email: {seeker.email}

Next Steps:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. An appointment has been created in your calendar
2. You can now communicate with the client through the app
3. Complete the service as agreed
4. Mark the appointment as complete when finished

Thank you for being part of our community!

Best regards,
Neighbor Service Team
"""
    
    email = EmailMessage(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [provider.email],
    )
    
    try:
        email.send()
        return True
    except Exception as e:
        print(f"Error sending proposal approval email: {e}")
        return False
