import pytest
from django.db import connections
from django.db.utils import OperationalError
from django.urls import reverse
from django.conf import settings

@pytest.mark.django_db
def test_database_connectivity():
    """Verify that the application can connect to the database."""
    db_conn = connections['default']
    try:
        c = db_conn.cursor()
    except OperationalError:
        pytest.fail("Database connection failed")
    else:
        assert True

def test_settings_configured():
    """Verify that critical settings are loaded."""
    assert settings.SECRET_KEY is not None
    assert settings.INSTALLED_APPS is not None

class TestSmoke:
    def test_basic_assertion(self):
        """Sanity check to ensure pytest is working."""
        assert 1 + 1 == 2
