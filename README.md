# Neighbor Service Backend

The backend is built with Django and Django REST Framework. It handles user authentication, service management, payments, and real-time communications.

## Setup

### Environment Variables
Ensure you have a `.env` file in the `backend/` root (or `ns_backend/` directory depending on your configuration preference, typically root).
Key variables:
- `DEBUG`: Set to `True` for development.
- `SECRET_KEY`: Django secret key.
- `topics`: Database configuration.

### Installation
```bash
pip install -r requirements.txt
```

### Database
Run migrations to set up the schema:
```bash
python manage.py migrate
```

### Running the Server
```bash
python manage.py runserver
```

## Common Commands

### Creating a Superuser
To access the Django Admin:
```bash
python manage.py createsuperuser
```

### Celery Workers
To run background tasks (requires Redis):
```bash
# Start Worker
celery -A ns_backend worker -l info

# Start Beat (Scheduler)
celery -A ns_backend beat -l info
```

### Running Tests
(Coming soon)
```bash
# pytest
```
