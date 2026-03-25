from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView, ProfileViewSet, PortfolioViewSet, 
    ServicePackageViewSet, ResendOTPView, ChangePasswordView, 
    PasswordResetRequestView, PasswordResetConfirmView,
    PasswordResetOTPConfirmView, AboutViewSet,
    VerifyOTPView, VerifyEmailView, GoogleLoginView,
    CustomTokenObtainPairView, LegalDocumentView
)

router = DefaultRouter()
router.register(r'profile', ProfileViewSet)
router.register(r'about', AboutViewSet, basename='about')
router.register(r'portfolio', PortfolioViewSet, basename='portfolio')
router.register(r'service-packages', ServicePackageViewSet, basename='service-packages')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend_otp'),
    path('verify/<str:uidb64>/<str:token>/', VerifyEmailView.as_view(), name='verify_email'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset-otp-confirm/', PasswordResetOTPConfirmView.as_view(), name='password_reset_otp_confirm'),
    path('login-google/', GoogleLoginView.as_view(), name='login_google'),
    path('legal/', LegalDocumentView.as_view(), name='legal_document'),
    path('', include(router.urls)),
]
