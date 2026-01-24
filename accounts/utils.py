from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def send_otp_email(user, otp):
    """
    Sends an OTP verification email to the user.
    Uses an HTML template and creates a plain-text fallback.
    """
    subject = 'Verify your email address - Neighbor Service'
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email
    
    context = {'otp': otp}
    html_content = render_to_string('accounts/emails/otp_email.html', context)
    text_content = strip_tags(html_content)  # Strip HTML tags for the text version

    try:
        from django.core.mail import send_mail
        send_mail(
            subject,
            text_content,
            from_email,
            [to_email],
            html_message=html_content,
            fail_silently=False
        )
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False
