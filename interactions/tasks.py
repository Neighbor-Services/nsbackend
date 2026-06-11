from celery import shared_task
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .utils import generate_ics_content
from accounts.models import Profile

def send_appointment_reminder_email(appointment, reminder_type):
    """
    Sends an appointment reminder email to the seeker and provider.
    """
    subject = f'Reminder: {appointment.title or "Service Appointment"} ({reminder_type})'
    provider = Profile.objects.get(user=appointment.provider)
    seeker = Profile.objects.get(user=appointment.seeker)
    # Format time for display
    start_time = appointment.appointment_date
    if not start_time:
        return False
        
    time_str = start_time.strftime('%B %d, %Y at %I:%M %p')
    
    body = f"""Hello,

This is a reminder for your upcoming appointment.

Appointment Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: {appointment.title or "Service Appointment"}
Scheduled Time: {time_str}
Provider: {provider.first_name}
Seeker: {seeker.first_name}

Please ensure you are ready and available at the scheduled time.

Best regards,
Neighbor Service Team
"""
    
    # Send to both seeker and provider
    email = EmailMessage(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [appointment.seeker.email, appointment.provider.email],
    )
    
    # Attach .ics
    ics_content = generate_ics_content(appointment)
    if ics_content:
        email.attach('appointment.ics', ics_content, 'text/calendar')
    
    try:
        email.send()
        return True
    except Exception as e:
        print(f"Error sending reminder email: {e}")
        return False

@shared_task(bind=True, max_retries=3)
def send_appointment_reminder_task(self, appointment_id, reminder_type):
    """
    Celery task to send a specific reminder.
    """
    try:
        from .models import Appointment
        appointment = Appointment.objects.select_related('seeker', 'provider').get(id=appointment_id)
        
        success = send_appointment_reminder_email(appointment, reminder_type)
        if success:
            if reminder_type == '24 Hours Before':
                appointment.reminder_day_sent = True
            elif reminder_type == '1 Hour Before':
                appointment.reminder_hour_sent = True
            appointment.save(update_fields=['reminder_day_sent', 'reminder_hour_sent'])
            return f"Reminder ({reminder_type}) sent for appointment {appointment_id}"
        else:
            raise Exception("Failed to send reminder email")
            
    except Appointment.DoesNotExist:
        return f"Appointment {appointment_id} not found"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@shared_task
def check_upcoming_appointments():
    """
    Periodic task to check for upcoming appointments and send reminders.
    Runs every 15 minutes.
    """
    from .models import Appointment
    now = timezone.now()
    
    # 1. Check for 24-hour reminders
    # Find appointments starting between (now + 23h 45m) and (now + 24h 15m)
    day_start = now + timedelta(hours=23, minutes=45)
    day_end = now + timedelta(hours=24, minutes=15)
    
    upcoming_day = Appointment.objects.filter(
        status='SCHEDULED',
        appointment_date__range=(day_start, day_end),
        reminder_day_sent=False
    )
    
    for appt in upcoming_day:
        send_appointment_reminder_task.delay(str(appt.id), '24 Hours Before')
        
    # 2. Check for 1-hour reminders
    # Find appointments starting between (now + 45m) and (now + 1h 15m)
    hour_start = now + timedelta(minutes=45)
    hour_end = now + timedelta(hours=1, minutes=15)
    
    upcoming_hour = Appointment.objects.filter(
        status='SCHEDULED',
        appointment_date__range=(hour_start, hour_end),
        reminder_hour_sent=False
    )
    
    for appt in upcoming_hour:
        send_appointment_reminder_task.delay(str(appt.id), '1 Hour Before')
        
    return f"Checked for reminders. Sent: {upcoming_day.count()} (24h), {upcoming_hour.count()} (1h)"

@shared_task(bind=True, max_retries=3)
def send_appointment_confirmation_email_task(self, appointment_id):
    """
    Celery task to send an appointment confirmation email to the seeker.
    """
    try:
        from .models import Appointment
        from .utils import send_appointment_confirmation_email
        appointment = Appointment.objects.select_related('seeker', 'provider').get(id=appointment_id)
        
        success = send_appointment_confirmation_email(appointment)
        if not success:
            raise Exception("Failed to send appointment confirmation email")
            
        return f"Appointment confirmation email sent to {appointment.seeker.email}"
        
    except Appointment.DoesNotExist:
        return f"Appointment {appointment_id} not found"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
