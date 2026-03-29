import os
import django
import sys

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ns_backend.settings')
django.setup()

from interactions.models import Appointment
from chat.models import Message

def sync_dates():
    print("Syncing Appointment dates...")
    appointments = Appointment.objects.all()
    count = 0
    for appt in appointments:
        if not appt.appointment_date:
            appt.appointment_date = appt.scheduled_time or appt.start_date
            if appt.appointment_date:
                appt.save()
                count += 1
    print(f"Synced {count} appointments.")

    print("Syncing Message calendar dates...")
    messages = Message.objects.filter(is_calender=True)
    msg_count = 0
    for msg in messages:
        if not msg.calender_date:
            msg.calender_date = msg.calender_start_date
            if msg.calender_date:
                msg.save()
                msg_count += 1
    print(f"Synced {msg_count} messages.")

if __name__ == "__main__":
    sync_dates()
