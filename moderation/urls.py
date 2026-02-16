from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReportViewSet, ProviderVerificationViewSet

router = DefaultRouter()
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'verifications', ProviderVerificationViewSet, basename='verification')

urlpatterns = [
    path('', include(router.urls)),
]
