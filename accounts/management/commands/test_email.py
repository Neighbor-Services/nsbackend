from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
import sys

class Command(BaseCommand):
    help = 'Tests email configuration by sending a test email to the specified address.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='The email address to send the test message to')

    def handle(self, *args, **options):
        email_address = options['email']
        
        self.stdout.write(self.style.WARNING(f'Attempting to send test email to: {email_address}'))
        
        # 1. Print Configuration (Masking sensitive info)
        self.stdout.write(self.style.SUCCESS('--- EMail Configuration ---'))
        self.stdout.write(f"EMAIL_BACKEND: {getattr(settings, 'EMAIL_BACKEND', 'Not Set')}")
        self.stdout.write(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'Not Set')}")
        self.stdout.write(f"EMAIL_PORT: {getattr(settings, 'EMAIL_PORT', 'Not Set')}")
        self.stdout.write(f"EMAIL_USE_TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Not Set')}")
        
        host_user = getattr(settings, 'EMAIL_HOST_USER', None)
        if host_user:
            self.stdout.write(f"EMAIL_HOST_USER: {host_user}")
        else:
             self.stdout.write(self.style.ERROR("EMAIL_HOST_USER: Not Set (or None)"))

        host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
        if host_pass:
            masked_pass = host_pass[:2] + '*' * (len(host_pass) - 2) if len(host_pass) > 2 else '****'
            self.stdout.write(f"EMAIL_HOST_PASSWORD: {masked_pass} (Length: {len(host_pass)})")
        else:
             self.stdout.write(self.style.ERROR("EMAIL_HOST_PASSWORD: Not Set (or None)"))
             
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not Set')}")
        self.stdout.write('---------------------------')

        # 2. Attempt Send
        try:
            subject = 'Test Email from Neighbor Service Debugger'
            message = 'This is a test email to verify the SMTP configuration. If you received this, the system is working.'
            from_email = settings.DEFAULT_FROM_EMAIL
            
            self.stdout.write("Sending...")
            result = send_mail(
                subject,
                message,
                from_email,
                [email_address],
                fail_silently=False,
            )
            
            if result == 1:
                self.stdout.write(self.style.SUCCESS(f'Successfully sent basic email to {email_address}'))
            else:
                self.stdout.write(self.style.WARNING(f'Basic email sent but return code was: {result}'))
                
            # 3. Test send_otp_email specifically (Template Check)
            self.stdout.write('---------------------------')
            self.stdout.write("Testing application's send_otp_email function...")
            from accounts.utils import send_otp_email
            from accounts.models import User
            
            # Create dummy user object for interface compatibility
            class DummyUser:
                email = email_address
                first_name = "Debug User"
                
            success = send_otp_email(DummyUser(), "123456")
            if success:
                 self.stdout.write(self.style.SUCCESS(f'Successfully sent OTP email via app logic to {email_address}'))
            else:
                 self.stdout.write(self.style.ERROR(f'FAILED to send OTP email via app logic.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'FAILED to send email.'))
            self.stdout.write(self.style.ERROR(f'Error Type: {type(e).__name__}'))
            self.stdout.write(self.style.ERROR(f'Error Message: {str(e)}'))
            
            import traceback
            self.stdout.write(traceback.format_exc())
