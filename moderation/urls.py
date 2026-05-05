from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReportViewSet, ProviderVerificationViewSet, BackgroundCheckViewSet, checkr_webhook_view

router = DefaultRouter()
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'verifications', ProviderVerificationViewSet, basename='verification')
router.register(r'background-checks', BackgroundCheckViewSet, basename='background-check')

urlpatterns = [
    path('', include(router.urls)),

    # Checkr webhook — no authentication, signature-verified internally
    path('checkr-webhook/', checkr_webhook_view, name='checkr-webhook'),
]
