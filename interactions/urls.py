from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FavoriteViewSet, ReviewViewSet, AppointmentViewSet, DisputeViewSet

router = DefaultRouter()
router.register(r'favorites', FavoriteViewSet)
router.register(r'reviews', ReviewViewSet)
router.register(r'appointments', AppointmentViewSet)
router.register(r'disputes', DisputeViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
