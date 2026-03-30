from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, DeviceTokenViewSet

router = DefaultRouter()
router.register(r'tokens', DeviceTokenViewSet)
router.register(r'', NotificationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
