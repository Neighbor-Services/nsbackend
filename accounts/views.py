from rest_framework import generics, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import update_session_auth_hash
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
import random
from django.utils import timezone
from datetime import timedelta
from .models import User, Profile, PortfolioItem, ServicePackage, About, LegalDocument
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
        print(f"DEBUG: Registering user {user.email}, sending OTP...")
        success = send_otp_email(user, otp)
        print(f"DEBUG: Email send result for {user.email}: {success}")

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
                user.otp_expiry = timezone.now() + timedelta(minutes=10)
                user.save()
                
                # Send OTP via email using helper
                print(f"DEBUG: Resending OTP to {user.email}...")
                success = send_otp_email(user, otp)
                print(f"DEBUG: Email send result for {user.email}: {success}")
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
        
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius')

        if lat and lng and radius:
            from ns_backend.utils import haversine_distance
            radius = float(radius)
            lat = float(lat)
            lng = float(lng)
            
            # 1. Bounding Box Filter
            lat_delta = radius / 111.0
            import math
            lng_delta = radius / (111.0 * math.cos(math.radians(lat)))
            
            queryset = queryset.filter(
                latitude__gte=lat - lat_delta,
                latitude__lte=lat + lat_delta,
                longitude__gte=lng - lng_delta,
                longitude__lte=lng + lng_delta
            )
            
            # 2. Haversine
            ids = []
            for item in queryset:
                dist = haversine_distance(lat, lng, item.latitude, item.longitude)
                if dist is not None and dist <= radius:
                    ids.append(item.id)
            queryset = queryset.filter(id__in=ids)
            
        return queryset

    def get_object(self):
        return Profile.objects.filter(user=self.request.user).first()

    @action(detail=False, methods=['get'])
    def me(self, request):
        profile = self.get_object()
        if not profile:
            # Lazy creation for users who registered before autonomic creation was added
            profile = Profile.objects.create(user=request.user)
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
        doc = LegalDocument.objects.filter(doc_type=doc_type, is_active=True).first()
        if not doc:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(doc)
        return Response(serializer.data)
