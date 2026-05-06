from rest_framework import generics, viewsets, permissions, status
from rest_framework.decorators import action
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import urlencode
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import update_session_auth_hash
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
import random
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .models import (
    User, Profile, About, PortfolioItem, ServicePackage,
    LegalDocument
)
from .serializers import (
    UserSerializer, ProfileSerializer, PortfolioItemSerializer, 
    ServicePackageSerializer, AboutSerializer,
    PasswordChangeSerializer, PasswordResetRequestSerializer, 
    PasswordResetConfirmSerializer, PasswordResetOTPSerializer,
    OTPSerializer, ResendOTPSerializer, CustomTokenObtainPairSerializer,
    LegalDocumentSerializer
)
from .utils import send_otp_email
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from .filters import ProfileFilter

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        
        # Automatically create a profile for the user
        Profile.objects.create(user=user)
        
        otp = str(random.randint(1000, 9999))
        user.otp_code = otp
        user.otp_expiry = timezone.now() + timedelta(minutes=10)
        user.save()
        
        # Send OTP via email using helper
        send_otp_email(user, otp)

class VerifyOTPView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = OTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp_code = serializer.validated_data['otp_code']
            user = User.objects.filter(email=email).first()

            if user and user.otp_code == otp_code and user.otp_expiry > timezone.now():
                user.is_verified = True
                user.otp_code = None
                user.otp_expiry = None
                user.save()
                return Response({"detail": "Email verified successfully."}, status=status.HTTP_200_OK)
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = ResendOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = User.objects.filter(email=email).first()
            if user:
                otp = str(random.randint(1000, 9999))
                user.otp_code = otp
                user.otp_expiry = timezone.now() + timedelta(minutes=10)
                user.save()
                send_otp_email(user, otp)
            return Response({"detail": "If an account exists, a new OTP has been sent."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyEmailView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.is_verified = True
            user.save()
            return Response({"detail": "Email verified successfully."}, status=status.HTTP_200_OK)
        return Response({"detail": "Invalid verification link."}, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = PasswordChangeSerializer
    model = User
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)
            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()
            update_session_auth_hash(request, self.object)
            return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = User.objects.filter(email=email).first()
            if user:
                otp = str(random.randint(1000, 9999))
                user.otp_code = otp
                user.otp_expiry = timezone.now() + timedelta(minutes=10)
                user.save()
                
                # Send OTP via email
                send_otp_email(user, otp)
                
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                print(f"Password Reset Link (Legacy): /api/v1/accounts/password-reset-confirm/{uid}/{token}/")
                print(f"Password Reset OTP: {otp}")
            return Response({"detail": "If an account exists with this email, a reset OTP has been sent."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            uidb64 = serializer.validated_data['uidb64']
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            try:
                uid = force_str(urlsafe_base64_decode(uidb64))
                user = User.objects.get(pk=uid)
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                user = None

            if user is not None and default_token_generator.check_token(user, token):
                user.set_password(new_password)
                user.save()
                return Response({"detail": "Password has been reset successfully."}, status=status.HTTP_200_OK)
            return Response({"detail": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.select_related('user', 'catalog_service').prefetch_related('portfolio_items', 'service_packages').all()
    serializer_class = ProfileSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProfileFilter
    search_fields = ['first_name', 'last_name', 'service', 'city']
    ordering_fields = ['average_rating', 'total_reviews', 'created_at']

    def create(self, request, *args, **kwargs):
        # Handle "upsert": if profile exists, update it.
        profile = Profile.objects.filter(user=request.user).first()
        if profile:
            serializer = self.get_serializer(profile, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response({"profile": serializer.data}, status=status.HTTP_200_OK)
        
        # Otherwise, create it (default behavior)
        # We need to manually inject the user if it's not in validated_data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response({"profile": serializer.data}, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            # Add providers key for frontend compatibility
            response.data['providers'] = response.data.pop('results', [])
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"providers": serializer.data})

    def get_queryset(self):
        queryset = self.queryset

        # Hide unverified providers from public listings unless requested by themselves or staff
        if not self.request.user.is_staff:
            from django.db.models import Q
            # Keep seekers, keep verified providers, keep the user's own profile
            queryset = queryset.filter(
                Q(user_type='SEEKER') | 
                Q(user_type='PROVIDER', is_identity_verified=True) | 
                Q(user=self.request.user)
            )

        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius')

        if lat and lng and radius:
            from django.db.models import FloatField, ExpressionWrapper
            from django.db.models.functions import ACos, Cos, Sin, Radians
            from django.db.models import F, Value
            from django.db.models.functions import Cast
            import math

            radius_km = float(radius)
            lat_f = float(lat)
            lng_f = float(lng)

            # Bounding box pre-filter (cheap index scan)
            lat_delta = radius_km / 111.0
            lng_delta = radius_km / (111.0 * math.cos(math.radians(lat_f)))
            queryset = queryset.filter(
                latitude__gte=lat_f - lat_delta,
                latitude__lte=lat_f + lat_delta,
                longitude__gte=lng_f - lng_delta,
                longitude__lte=lng_f + lng_delta,
            ).exclude(latitude__isnull=True).exclude(longitude__isnull=True)

            # DB-level Haversine — eliminates Python loop over every profile
            lat_rad = math.radians(lat_f)
            lng_rad = math.radians(lng_f)
            queryset = queryset.annotate(
                distance_km=ExpressionWrapper(
                    Value(6371.0) * ACos(
                        Sin(Value(lat_rad)) * Sin(Radians(Cast(F('latitude'), FloatField())))
                        + Cos(Value(lat_rad)) * Cos(Radians(Cast(F('longitude'), FloatField())))
                        * Cos(Value(lng_rad) - Radians(Cast(F('longitude'), FloatField()))),
                        output_field=FloatField(),
                    ),
                    output_field=FloatField(),
                )
            ).filter(distance_km__lte=radius_km).order_by('distance_km')

        # Popular filter
        popular = self.request.query_params.get('popular') == 'true'
        if popular:
            # Verified providers only, sorted by rating
            queryset = queryset.filter(user_type='PROVIDER', is_identity_verified=True).order_by('-average_rating', '-total_reviews')[:10]

        return queryset

    def get_object(self):
        return Profile.objects.filter(user=self.request.user).first()

    @action(detail=False, methods=['get'])
    def me(self, request):
        profile = self.get_object()
        if not profile:
            # Lazy creation for users who registered before autonomic creation was added
            profile = Profile.objects.create(user=request.user)
        
        # Trigger streak and activity check
        profile.record_activity()
        
        serializer = self.get_serializer(profile)
        return Response({"profile": serializer.data})

    @action(detail=False, methods=['patch', 'put'])
    def update_me(self, request):
        profile = self.get_object()
        if not profile:
            profile = Profile.objects.create(user=request.user)
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"profile": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['patch'], url_path='picture')
    def picture(self, request):
        profile = self.get_object()
        if not profile:
            profile = Profile.objects.create(user=request.user)
        
        if 'image' in request.FILES:
            profile.profile_picture = request.FILES['image']
            profile.save()
            return Response({"profile": self.get_serializer(profile).data})
        return Response({"detail": "No image provided"}, status=status.HTTP_400_BAD_REQUEST)

class PortfolioViewSet(viewsets.ModelViewSet):
    queryset = PortfolioItem.objects.select_related('profile', 'profile__user').all()
    serializer_class = PortfolioItemSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(profile=self.request.user.profile)

    def get_queryset(self):
        queryset = self.queryset
        profile_id = self.request.query_params.get('profile_id')
        if profile_id:
            queryset = queryset.filter(profile_id=profile_id)
        
        # Popularity filter
        popular = self.request.query_params.get('popular') == 'true'
        if popular:
            queryset = queryset.order_by('-profile__average_rating', '-profile__total_reviews')
            
        return queryset

class AboutViewSet(viewsets.ModelViewSet):
    queryset = About.objects.select_related('user').all()
    serializer_class = AboutSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def user(self, request):
        user_id = request.query_params.get('user_id')
        about = self.queryset.filter(user_id=user_id).first()
        profile = Profile.objects.filter(user_id=user_id).first()
        
        return Response({
            "about": AboutSerializer(about).data if about else None,
            "user": ProfileSerializer(profile).data if profile else None
        })

class ServicePackageViewSet(viewsets.ModelViewSet):
    queryset = ServicePackage.objects.all()
    serializer_class = ServicePackageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(profile=self.request.user.profile)

    def get_queryset(self):
        profile_id = self.request.query_params.get('profile_id')
        if profile_id:
            return self.queryset.filter(profile_id=profile_id)
        return self.queryset

class PasswordResetOTPConfirmView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = PasswordResetOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp_code = serializer.validated_data['otp_code']
            new_password = serializer.validated_data['new_password']
            
            user = User.objects.filter(email=email).first()
            if user and user.otp_code == otp_code and user.otp_expiry > timezone.now():
                user.set_password(new_password)
                user.otp_code = None
                user.otp_expiry = None
                user.save()
                return Response({"detail": "Password has been reset successfully."}, status=status.HTTP_200_OK)
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken
import jwt

class GoogleLoginView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        token = request.data.get('id_token')
        if not token:
             return Response({"detail": "id_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Verify the token
            # We skip client_id check here to allow any valid Google ID token for simplicity across Android/iOS/Web
            # In a strict environment, pass the expected CLIENT_ID as the second argument.
            id_info = id_token.verify_oauth2_token(token, google_requests.Request())
            
            email = id_info['email']
            first_name = id_info.get('given_name', '')
            last_name = id_info.get('family_name', '')
            
            # Upsert user
            user, created = User.objects.get_or_create(email=email, defaults={
                'is_verified': True
            })
            
            if created:
                user.set_unusable_password()
                user.save()
                # Create profile with name from Google
                Profile.objects.create(user=user, first_name=first_name, last_name=last_name)
            else:
                # Update existing user verification if needed
                if not user.is_verified:
                    user.is_verified = True
                    user.save()
            
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'authentication_token': str(refresh.access_token),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"detail": f"Invalid token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class AppleLoginView(generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        token = request.data.get('id_token')
        if not token:
             return Response({"detail": "id_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            apple_jwks_url = 'https://appleid.apple.com/auth/keys'
            jwks_client = jwt.PyJWKClient(apple_jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            
            # Verify the token
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )
            
            email = decoded.get('email')
            if not email:
                return Response({"detail": "No email provided by Apple check."}, status=status.HTTP_400_BAD_REQUEST)
                
            # Upsert user
            user, created = User.objects.get_or_create(email=email, defaults={
                'is_verified': True
            })
            
            # Apple only provides name on the first login, so frontend should pass it
            first_name = request.data.get("first_name", "")
            last_name = request.data.get("last_name", "")
            
            if created:
                user.set_unusable_password()
                user.save()
                Profile.objects.create(user=user, first_name=first_name, last_name=last_name)
            else:
                if not user.is_verified:
                    user.is_verified = True
                    user.save()
            
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'authentication_token': str(refresh.access_token),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({"detail": f"Invalid token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class DeleteAccountView(generics.DestroyAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    
    def delete(self, request, *args, **kwargs):
        user = request.user
        user.delete()
        return Response({"detail": "Account deleted successfully."}, status=status.HTTP_200_OK)


class LegalDocumentView(generics.GenericAPIView):
    """Public endpoint to get Terms & Conditions or Privacy Policy."""
    permission_classes = (permissions.AllowAny,)
    serializer_class = LegalDocumentSerializer

    def get(self, request):
        doc_type = request.query_params.get('type', '').upper()
        if doc_type not in ('TERMS', 'PRIVACY'):
            return Response(
                {"detail": "type must be TERMS or PRIVACY"},
                status=status.HTTP_400_BAD_REQUEST
            )

        cache_key = f"legal_docs_{doc_type}"
        data = cache.get(cache_key)

        if data is None:
            docs = LegalDocument.objects.filter(doc_type=doc_type, is_active=True).order_by('created_at')
            if not docs.exists():
                return Response(
                    {"detail": "Documents not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
            serializer = self.get_serializer(docs, many=True)
            data = serializer.data
            cache.set(cache_key, data, 60 * 60 * 24)  # Cache for 24 hours

        return Response(data)

@csrf_exempt
def apple_callback_view(request):
    """
    Apple Sign In callback view for Android.
    Apple sends a POST request with token data here. We bounce it back
    to the Android app using a custom intent scheme.
    """
    if request.method == 'POST':
        data = request.POST.dict()
        query_string = urlencode(data)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Sign In with Apple</title></head>
        <body>
          <script>
            // For Android Chrome, the recommended way is the intent:// scheme
            var intentUrl = "intent://callback?{query_string}#Intent;package=com.neighborservicesolutionsllc.nsapp;scheme=signinwithapple;end;";
            
            window.location.href = intentUrl;
            
            // Fallback for iOS or other browsers
            setTimeout(function() {{
                window.location.href = "signinwithapple://callback?{query_string}";
            }}, 1000);
          </script>
        </body>
        </html>
        """
        return HttpResponse(html)
    return HttpResponse("This endpoint only accepts POST requests from Apple.", status=405)
