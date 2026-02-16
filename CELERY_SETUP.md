# Celery Setup Instructions

## Installation

1. **Install Celery dependencies:**
   ```bash
   pip install -r celery_requirements.txt
   ```

2. **Ensure Redis is running:**
   ```bash
   # Windows (if using Redis for Windows)
   redis-server
   
   # Linux/Mac
   redis-server
   
   # Or use Docker
   docker run -d -p 6379:6379 redis:alpine
   ```

## Running Celery

### Development

Open two new terminals and run:

1. **Celery Worker**:
```bash
cd e:\ns\backend
celery -A ns_backend worker -l info
```

2. **Celery Beat** (Required for reminders):
```bash
cd e:\ns\backend
celery -A ns_backend beat -l info
```

### Production

Use a process manager like systemd or supervisor. You will need one service for the worker and one for the beat.

**Systemd Worker Example** (`/etc/systemd/system/celery.service`):
```ini
[Unit]
Description=Celery Worker Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/backend
ExecStart=/path/to/venv/bin/celery -A ns_backend worker --loglevel=info

[Install]
WantedBy=multi-user.target
```

**Systemd Beat Example** (`/etc/systemd/system/celerybeat.service`):
```ini
[Unit]
Description=Celery Beat Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/backend
ExecStart=/path/to/venv/bin/celery -A ns_backend beat --loglevel=info

[Install]
WantedBy=multi-user.target
```

## Monitoring (Optional)

Install Flower for web-based monitoring:

```bash
pip install flower
celery -A ns_backend flower
```

Access at: http://localhost:5555

## Environment Variables

Add to `.env` (optional, defaults to localhost):

```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

## Testing

1. Start Django server: `python manage.py runserver`
2. Start Celery worker: `celery -A ns_backend worker -l info`
3. Start Celery beat: `celery -A ns_backend beat -l info`
4. Approve a proposal via API to create an appointment.
5. Create a test appointment in the Django admin with a `scheduled_time` exactly 24 hours (or 1 hour) from now.
6. Check Celery logs for the reminder task execution.
7. Verify both seeker and provider receive the reminder email.
