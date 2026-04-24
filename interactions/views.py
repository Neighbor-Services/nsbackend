from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from django.db import models, transaction
import decimal
from .models import Favorite, Review, Appointment, Dispute
from .serializers import FavoriteSerializer, ReviewSerializer, AppointmentSerializer, DisputeSerializer
from payments.models import Wallet, WalletTransaction
from accounts.models import Profile
from notifications.utils import send_notification

class FavoriteViewSet(viewsets.ModelViewSet):
    queryset = Favorite.objects.select_related('user', 'favorite_user').all()
    serializer_class = FavoriteSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Handle "provider" key from frontend
        favorite_user_id = request.data.get('provider') or request.data.get('favorite_user_id')
        if not favorite_user_id:
            return Response({"error": "favorite_user_id or provider required"}, status=status.HTTP_400_BAD_REQUEST)
            
        favorite, created = Favorite.objects.get_or_create(
            user=request.user,
            favorite_user_id=favorite_user_id
        )
        serializer = self.get_serializer(favorite)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('reviewer', 'provider', 'provider__profile').all()
    serializer_class = ReviewSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_queryset(self):
        queryset = self.queryset
        provider_id = self.request.query_params.get('provider', None)
        if provider_id is not None:
            queryset = queryset.filter(
                models.Q(provider__id=provider_id) | 
                models.Q(provider__profile__id=provider_id)
            )
        return queryset

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        review = serializer.save(reviewer=self.request.user)
        provider = review.provider

        # Single aggregate query instead of fetching all review objects
        from django.db.models import Avg, Count
        agg = Review.objects.filter(provider=provider).aggregate(
            avg=Avg('rating'), total=Count('id')
        )
        provider.profile.average_rating = agg['avg'] or 0
        provider.profile.total_reviews = agg['total'] or 0
        provider.profile.save()

        # Notify Provider
        send_notification(
            user=provider,
            sender=review.reviewer,
            title="New Review!",
            message=f"A seeker has left you a {review.rating}-star review.",
            notification_type="SYSTEM", # Or add 'REVIEW' type later
            data={"review_id": str(review.id)}
        )

class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.select_related(
        'seeker', 'provider',
        'seeker__profile', 'provider__profile',
        'service_request', 'service_request__user', 'service_request__user__profile',
        'proposal', 'proposal__request', 'proposal__request__user',
    ).prefetch_related(
        'service_request__proposals',
    ).all()
    serializer_class = AppointmentSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            wrapped_data = self._wrap_appointments(serializer.data, request.user)
            return self.get_paginated_response(wrapped_data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(self._wrap_appointments(serializer.data, request.user))

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        # Wrap single appointment similar to list format
        wrapped_data = self._wrap_appointments([serializer.data], request.user)[0]
        return Response(wrapped_data)

    @action(detail=True, methods=['post'], url_path='verify-code')
    def verify_code(self, request, pk=None):
        appointment = self.get_object()
        
        # Only Provider should be verifying the code
        if request.user != appointment.provider:
            return Response({'error': 'Only the provider can verify the arrival code'}, status=status.HTTP_403_FORBIDDEN)
            
        code = request.data.get('code')
        if not code:
            return Response({'error': 'Verification code required'}, status=status.HTTP_400_BAD_REQUEST)
            
        if appointment.status == 'COMPLETED':
            return Response({'error': 'Appointment is already completed'}, status=status.HTTP_400_BAD_REQUEST)
            
        if appointment.status == 'IN_PROGRESS':
            return Response({'error': 'Appointment is already verified and in progress'}, status=status.HTTP_400_BAD_REQUEST)
            
        if str(code).strip().upper() == str(appointment.secret_code).strip().upper():
            appointment.status = 'IN_PROGRESS'
            appointment.save()
            
            # Notify Seeker
            send_notification(
                user=appointment.seeker,
                sender=appointment.provider,
                title="Provider Arrived!",
                message=f"The provider has successfully verified your secret code. Service is now in progress.",
                notification_type="APPOINTMENT",
                data={"appointment_id": str(appointment.id)}
            )
            
            serializer = self.get_serializer(appointment)
            wrapped_data = self._wrap_appointments([serializer.data], request.user)[0]
            return Response({'status': 'verified', 'data': wrapped_data})
        else:
            return Response({'error': 'Invalid verification code. Please check with the seeker.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        appointment = self.get_object()
        
        # Security: Only Seeker or Provider can complete
        if request.user not in [appointment.seeker, appointment.provider]:
            return Response({'error': 'Not authorized'}, status=status.HTTP_401_UNAUTHORIZED)
            
        if appointment.status == 'COMPLETED':
            return Response({'error': 'Appointment already completed'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            appointment.status = 'COMPLETED'
            appointment.save()
            
            if appointment.is_funded:
                # Release funds to Provider's Wallet
                amount = request.data.get('amount')
                if not amount:
                    return Response({'error': 'Completion amount required to release funds'}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    amount_decimal = decimal.Decimal(str(amount))
                except (decimal.InvalidOperation, ValueError):
                    return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Calculate Commission
                # Tiers: FREE (20%), SILVER (15%), GOLD (10%), PLATINUM (5%)
                tier = appointment.provider.profile.subscription_tier or 'FREE'
                commission_rates = {
                    'FREE': 0.20,
                    'SILVER': 0.15,
                    'GOLD': 0.10,
                    'PLATINUM': 0.05
                }
                rate = commission_rates.get(tier, 0.20)
                commission = amount_decimal * decimal.Decimal(str(rate))
                net_amount = amount_decimal - commission
                
                # Update Provider Wallet
                wallet, _ = Wallet.objects.get_or_create(user=appointment.provider)
                wallet.balance += net_amount
                wallet.save()
                
                # Create Transaction Record
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=net_amount,
                    transaction_type='CREDIT',
                    description=f'Job Completion: {appointment.title or "Service"}',
                    status='COMPLETED',
                    reference_id=str(appointment.id)
                )
                
                # Notify Seeker
                send_notification(
                    user=appointment.seeker,
                    sender=appointment.provider,
                    title="Service Completed!",
                    message=f"The provider has marked your service '{appointment.title}' as completed.",
                    notification_type="APPOINTMENT",
                    data={"appointment_id": str(appointment.id)}
                )
                
                return Response({
                    'status': 'appointment completed',
                    'funds_released': str(net_amount),
                    'commission_deducted': str(commission)
                })
                
    def create(self, request, *args, **kwargs):
        # Log incoming creation request
        print(f"Appointment creation request data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            # Wrap the newly created appointment for the response
            serializer = self.get_serializer(instance)
            wrapped_data = self._wrap_appointments([serializer.data], request.user)[0]
            # Notify Provider of new appointment
            send_notification(
                user=instance.provider,
                sender=request.user,
                title="New Appointment!",
                message=f"You have a new appointment for {instance.title}.",
                notification_type="APPOINTMENT",
                data={"appointment_id": str(instance.id)}
            )

            headers = self.get_success_headers(serializer.data)
            return Response(wrapped_data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            print(f"Appointment creation error: {str(e)}")
            if hasattr(serializer, 'errors'):
                print(f"Serializer errors: {serializer.errors}")
            return Response({'error': str(e), 'details': getattr(serializer, 'errors', {})}, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        # The logic is now inside create for better response wrapping
        pass

    def _wrap_appointments(self, data, current_user):
        wrapped = []
        for item in data:
            seeker_profile = item.get('seeker_profile')
            provider_profile = item.get('provider_profile')
            
            # robust comparison of UUIDs
            is_seeker = str(item.get('seeker')) == str(current_user.id)
            
            if is_seeker:
                user_profile = provider_profile
                role = 'seeker'
            else:
                user_profile = seeker_profile
                role = 'provider'
                
            wrapped.append({
                "appointment": item,
                "user": user_profile,
                "role": role
            })
        return wrapped

    def get_queryset(self):
        return self.queryset.filter(models.Q(seeker=self.request.user) | models.Q(provider=self.request.user))

class DisputeViewSet(viewsets.ModelViewSet):
    queryset = Dispute.objects.select_related('raised_by', 'defendant', 'appointment').all()
    serializer_class = DisputeSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_queryset(self):
        return self.queryset.filter(models.Q(raised_by=self.request.user) | models.Q(defendant=self.request.user))

    def create(self, request, *args, **kwargs):
        print(f"Dispute creation request data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            print(f"Dispute creation error: {str(e)}")
            print(f"Serializer errors: {serializer.errors if hasattr(serializer, 'errors') else 'No errors'}")
            raise

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_evidence(self, request, pk=None):
        dispute = self.get_object()
        
        if request.user not in [dispute.raised_by, dispute.defendant]:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
            
        file = request.FILES.get('evidence')
        if not file:
            return Response({'error': 'No evidence file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        dispute.evidence = file
        dispute.save()
        
        return Response({'status': 'evidence uploaded successfully'})

    def perform_create(self, serializer):
        dispute = serializer.save(raised_by=self.request.user)
        # Notify Defendant
        send_notification(
            user=dispute.defendant,
            sender=self.request.user,
            title="Dispute Raised",
            message=f"A dispute has been raised against you for an appointment.",
            notification_type="SYSTEM",
            data={"dispute_id": str(dispute.id)}
        )
