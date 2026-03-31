from django.core.mail import EmailMessage
from django.conf import settings
from datetime import timedelta

def generate_ics_content(appointment):
    """
    Generates iCalendar (.ics) content for the given appointment.
    """
    start_time = appointment.appointment_date
    if not start_time:
        return None
        
    end_time = start_time + timedelta(hours=1)
    
    dtstart = start_time.strftime('%Y%m%dT%H%M%SZ')
    dtend = end_time.strftime('%Y%m%dT%H%M%SZ')
    dtstamp = appointment.created_at.strftime('%Y%m%dT%H%M%SZ')
    
    uid = f"{appointment.id}@neighborservice.com"
    summary = appointment.title or f"Service Appointment: {appointment.seeker.email}"
    description = appointment.description or f"Appointment between {appointment.seeker.email} and {appointment.provider.email}"
    
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Neighbor Service//NONSGML v1.0//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    
    return "\n".join(ics_lines)

def send_appointment_confirmation_email(appointment):
    """
    Sends an appointment confirmation email to the seeker with an .ics attachment.
    """
    subject = f'Appointment Confirmed: {appointment.title or "Service"}'
    body = (
        f"Hello,\n\n"
        f"An appointment has been confirmed between {appointment.seeker.email} and {appointment.provider.email}.\n\n"
        f"Scheduled Time: {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p') if appointment.appointment_date else 'TBD'}\n\n"
        f"Please find the calendar invite attached.\n\n"
        f"Best regards,\nNeighbor Service Team"
    )
    
    email = EmailMessage(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [appointment.seeker.email, appointment.provider.email],
    )
    
    ics_content = generate_ics_content(appointment)
    if ics_content:
        email.attach('appointment.ics', ics_content, 'text/calendar')
    
    try:
        email.send()
        return True
    except Exception as e:
        print(f"Error sending appointment email: {e}")
        return False
