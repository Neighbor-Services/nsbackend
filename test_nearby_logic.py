import os
import django
import math
from django.db.models import F, FloatField
from django.db.models.functions import ACos, Cos, Radians, Sin, Cast

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ns_backend.settings')
django.setup()

from accounts.models import Profile

def test_nearby_providers(lat, lng, radius=25.0):
    lat_rad = math.radians(lat)
    lng_rad = math.radians(lng)

    nearby_providers = Profile.objects.filter(
        user_type='PROVIDER',
        # is_identity_verified=True, # Optional for test
        latitude__isnull=False,
        longitude__isnull=False
    ).annotate(
        distance=6371 * ACos(
            Sin(lat_rad) * Sin(Radians(Cast(F('latitude'), FloatField()))) +
            Cos(lat_rad) * Cos(Radians(Cast(F('latitude'), FloatField()))) *
            Cos(Radians(Cast(F('longitude'), FloatField())) - lng_rad),
            output_field=FloatField(),
        )
    ).filter(distance__lte=radius)

    print(f"Found {nearby_providers.count()} providers within {radius}km of ({lat}, {lng})")
    for p in nearby_providers:
        print(f"- {p.user.email}: {p.distance:.2f}km")

if __name__ == "__main__":
    # Test with some coordinates (e.g., center of a city)
    # You might need to adjust these based on your mock data
    test_nearby_providers(6.5244, 3.3792) # Lagos example
