"""
URL configuration for ns_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from payments.views import SubscriptionViewSet
from accounts.views import apple_callback_view

urlpatterns = [
    path('admin/', admin.path if hasattr(admin, 'path') else admin.site.urls),
    # Explicit override to fix routing conflict
    path('api/v1/subscription/create/', SubscriptionViewSet.as_view({'post': 'create_subscription'}), name='subscription-create-override'),
    
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/services/', include('services.urls')),
    path('api/v1/interactions/', include('interactions.urls')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/notifications/', include('notifications.urls')),
    # Flutter client calls /api/notifications/ (without v1 prefix) — support both
    path('api/notifications/', include('notifications.urls')),
    path('api/v1/moderation/', include('moderation.urls')),
    path('api/v1/audit/', include('audit.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/v1/wallet/', include('payments.urls')),
    path('api/v1/customer/', include('payments.urls')),
    path('api/v1/subscription/', include('payments.urls')),
    path('api/v1/consultations/', include('consultations.urls')),
    
    path('callbacks/apple', apple_callback_view, name='apple_callback'),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Public Website
    path('', include('public_site.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
