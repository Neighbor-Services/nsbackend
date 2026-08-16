from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from accounts.models import Profile
from notifications.utils import send_notification
from .models import Customer, Subscription, SubscriptionPlan, Wallet, PayoutRequest, WalletTransaction
from .serializers import (CustomerSerializer, SubscriptionSerializer, SubscriptionPlanSerializer,
                          WalletSerializer, WalletTransactionSerializer, PayoutRequestSerializer)
from django.db import transaction
from django.utils import timezone
import decimal
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
import stripe
from audit.utils import log_audit_action

stripe.api_key = settings.STRIPE_SECRET_KEY


class IAPReceiptThrottle(UserRateThrottle):
    """Limits receipt validation to 20 calls/minute per user to protect Google/Apple API quotas."""
    scope = 'iap_receipt'
    rate = '20/minute'


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def user(self, request):
        # Frontend may send user_id in data or query params
        user_id = request.data.get('user_id') or request.query_params.get('user_id')
        if not user_id:
            user_id = request.user.id
            
        customer, created = Customer.objects.get_or_create(user_id=user_id)
        
        if not customer.stripe_customer_id:
            try:
                stripe_customer = stripe.Customer.create(email=customer.user.email)
                customer.stripe_customer_id = stripe_customer.id
                customer.save()
            except Exception as e:
                print(f"Stripe Customer Creation Error: {e}")
            
        serializer = self.get_serializer(customer)
        return Response({"customer": serializer.data})

    def create(self, request, *args, **kwargs):
        # Handle /create (POST)
        customer, created = Customer.objects.get_or_create(user=request.user)
        if not customer.stripe_customer_id:
            try:
                stripe_customer = stripe.Customer.create(email=request.user.email)
                customer.stripe_customer_id = stripe_customer.id
                customer.save()
            except Exception as e:
                print(f"Stripe Customer Creation Error: {e}")
            
        serializer = self.get_serializer(customer)
        return Response({"customer": serializer.data}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['patch'])
    def ephmeral(self, request):
        customer, _ = Customer.objects.get_or_create(user=request.user)
        if not customer.stripe_customer_id:
            try:
                stripe_customer = stripe.Customer.create(email=request.user.email)
                customer.stripe_customer_id = stripe_customer.id
                customer.save()
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ephemeral_key = stripe.EphemeralKey.create(
                customer=customer.stripe_customer_id,
                stripe_version='2022-11-15'
            )
            customer.ephemeral_secret = ephemeral_key.secret
            customer.save()
            return Response({"customer": self.get_serializer(customer).data})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['patch'], url_path='paymentmethod/update')
    def update_payment_method(self, request):
        customer, _ = Customer.objects.get_or_create(user=request.user)
        payment_method_id = request.data.get('id')
        if not payment_method_id:
            return Response({'error': 'Payment method ID required'}, status=status.HTTP_400_BAD_REQUEST)
        
        customer.default_payment_method = payment_method_id
        customer.save()
        return Response({"customer": self.get_serializer(customer).data})

    @action(detail=False, methods=['post'], url_path='account/connect')
    def account_connect(self, request):
        customer, _ = Customer.objects.get_or_create(user=request.user)
        
        if not customer.stripe_account_id:
            try:
                account = stripe.Account.create(
                    type='express',
                    country='US',
                    email=request.user.email,
                    capabilities={
                        'card_payments': {'requested': True},
                        'transfers': {'requested': True},
                    },
                )
                customer.stripe_account_id = account.id
                customer.save()
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        return Response({"message": "Account connected successfully", "account_id": customer.stripe_account_id})

    @action(detail=False, methods=['post'])
    def transfer(self, request):
        amount = request.data.get('amount')
        user_id = request.data.get('user_id')
        
        if not amount or not user_id:
            return Response({'error': 'Amount and user_id required'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            target_customer = Customer.objects.get(user_id=user_id)
            if not target_customer.stripe_account_id:
                return Response({'error': 'Target user has no Stripe Connect account'}, status=status.HTTP_400_BAD_REQUEST)
                
            transfer = stripe.Transfer.create(
                amount=int(amount),
                currency='usd',
                destination=target_customer.stripe_account_id,
                description=f"Transfer from {request.user.email}"
            )
            return Response({"status": "Transfer successful", "transfer_id": transfer.id})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=False, methods=['post'], url_path='payment-sheet')
    def payment_sheet(self, request):
        customer, created = Customer.objects.get_or_create(user=request.user)
        
        if not customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=request.user.email)
            customer.stripe_customer_id = stripe_customer.id
            customer.save()
            
        ephemeral_key = stripe.EphemeralKey.create(
            customer=customer.stripe_customer_id,
            stripe_version='2022-11-15'
        )
        
        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount required'}, status=status.HTTP_400_BAD_REQUEST)
            
        payment_intent = stripe.PaymentIntent.create(
            amount=int(float(amount) * 100),
            currency='usd',
            customer=customer.stripe_customer_id,
            automatic_payment_methods={
                'enabled': True,
            },
        )
        
        return Response({
            'paymentIntent': payment_intent.client_secret,
            'ephemeralKey': ephemeral_key.secret,
            'customer': customer.stripe_customer_id,
            'publishableKey': settings.STRIPE_PUBLIC_KEY
        })

    @action(detail=False, methods=['post'], url_path='fund-appointment')
    def fund_appointment(self, request):
        from interactions.models import Appointment
        appointment_id = request.data.get('appointment_id')
        if not appointment_id:
            return Response({'error': 'Appointment ID required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            appointment = Appointment.objects.select_related(
                'seeker', 'provider'
            ).get(id=appointment_id, seeker=request.user)
        except Appointment.DoesNotExist:
            return Response({'error': 'Appointment not found or not owned by you'}, status=status.HTTP_404_NOT_FOUND)

        # Resolve provider's Stripe Connect account
        provider_wallet = Wallet.objects.filter(user=appointment.provider).first()
        if not provider_wallet or not provider_wallet.stripe_connect_id:
            return Response(
                {'error': 'Provider has not completed Stripe Connect onboarding and cannot receive payments.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        customer, created = Customer.objects.get_or_create(user=request.user)
        if not customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=request.user.email)
            customer.stripe_customer_id = stripe_customer.id
            customer.save()

        ephemeral_key = stripe.EphemeralKey.create(
            customer=customer.stripe_customer_id,
            stripe_version='2022-11-15'
        )

        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount required'}, status=status.HTTP_400_BAD_REQUEST)

        amount_cents = int(float(amount) * 100)

        # 5% platform fee — adjust PLATFORM_FEE_PERCENT in settings to override
        fee_percent = getattr(settings, 'PLATFORM_FEE_PERCENT', 5)
        application_fee = int(amount_cents * fee_percent / 100)

        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            customer=customer.stripe_customer_id,
            # Route directly to provider's Connect account
            transfer_data={
                'destination': provider_wallet.stripe_connect_id,
            },
            application_fee_amount=application_fee,
            metadata={
                'appointment_id': str(appointment.id),
                'provider_id': str(appointment.provider.id),
                'seeker_id': str(appointment.seeker.id),
                'type': 'job_funding',
            },
            automatic_payment_methods={
                'enabled': True,
            },
        )

        appointment.payment_intent_id = payment_intent.id
        appointment.save()

        log_audit_action(
            user=request.user,
            action='FUND_APPOINTMENT',
            resource_type='Appointment',
            resource_id=appointment.id,
            details={'amount': str(amount), 'payment_intent': payment_intent.id},
            request=request
        )

        return Response({
            'paymentIntent': payment_intent.client_secret,
            'ephemeralKey': ephemeral_key.secret,
            'customer': customer.stripe_customer_id,
            'publishableKey': settings.STRIPE_PUBLIC_KEY
        })

    @action(detail=False, methods=['post'], url_path='fund-background-check')
    def fund_background_check(self, request):
        customer, created = Customer.objects.get_or_create(user=request.user)
        if not customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=request.user.email)
            customer.stripe_customer_id = stripe_customer.id
            customer.save()

        ephemeral_key = stripe.EphemeralKey.create(
            customer=customer.stripe_customer_id,
            stripe_version='2022-11-15'
        )

        # Fetch fee from ModerationSetting
        from moderation.models import ModerationSetting
        setting = ModerationSetting.objects.first()
        fee = setting.background_check_fee if setting else 29.99
        amount_cents = int(float(fee) * 100)

        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            customer=customer.stripe_customer_id,
            metadata={
                'type': 'background_check',
                'user_id': str(request.user.id),
            },
            automatic_payment_methods={
                'enabled': True,
            },
        )

        log_audit_action(
            user=request.user,
            action='FUND_BACKGROUND_CHECK',
            resource_type='User',
            resource_id=request.user.id,
            details={'amount_cents': amount_cents, 'payment_intent': payment_intent.id},
            request=request
        )

        return Response({
            'paymentIntent': payment_intent.client_secret,
            'ephemeralKey': ephemeral_key.secret,
            'customer': customer.stripe_customer_id,
            'publishableKey': settings.STRIPE_PUBLIC_KEY,
            'amount_cents': amount_cents,
        })

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing available subscription plans"""
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = (permissions.AllowAny,)  # Allow anyone to view plans
    
    def get_queryset(self):
        """Return only active plans ordered by display_order"""
        return self.queryset.order_by('display_order', 'price')

class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='user/get')
    def user_get(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        if not subscription:
            return Response({"subscription": None}, status=status.HTTP_200_OK)

        # Rec #7: If is_active but next_payment is in the past, proactively mark inactive.
        # The S2S webhook should have caught this, but this is a safety net.
        if subscription.is_active and subscription.next_payment:
            if subscription.next_payment < timezone.now():
                subscription.is_active = False
                subscription.save(update_fields=['is_active', 'updated_at'])

        serializer = self.get_serializer(subscription)
        return Response({"subscription": serializer.data})

    @action(detail=False, methods=['delete'], url_path='user/delete')
    def user_delete(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        if subscription:
            user = request.user
            subscription.delete()
            
            profile = Profile.objects.filter(user=user).first()
            profile.catalog_services.clear()
            profile.service = ""
            profile.subscription_interval = "none"
            profile.save()
            
            send_notification(
                user=user,
                title="Subscription Canceled",
                message="You canceled your subscription plan",
                notification_type="SYSTEM",
                data={"ip": request.META.get('REMOTE_ADDR')}
            )
            log_audit_action(
                        user=request.user,
                        action='CANCEL SUBSCRIPTION',
                        resource_type='Subscription',
                        resource_id=request.user.id,
                        details={'method': 'credentials'},
                        request=request
                    )
            return Response({"message": "Subscription deleted"}, status=status.HTTP_200_OK)
        return Response({"message": "No subscription found"}, status=status.HTTP_404_NOT_FOUND)

class WalletViewSet(viewsets.ModelViewSet):
    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_throttles(self):
        if self.action == 'request_payout':
            self.throttle_scope = 'payout'
        return super().get_throttles()

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def my_wallet(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def transactions(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        transactions = wallet.transactions.all().order_by('-created_at')
        serializer = WalletTransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def request_payout(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        try:
            amount = decimal.Decimal(request.data.get('amount', 0))
        except (decimal.InvalidOperation, TypeError):
             return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)
        
        if amount <= 0:
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
        
        if wallet.balance < amount:
            return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not wallet.stripe_connect_id:
            return Response({'error': 'Stripe Connect account not found. Please onboard first.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # For Connect, we usually do a Transfer to the connected account
            # This pushes funds from the platform's Stripe balance to the provider's Connect account
            transfer = stripe.Transfer.create(
                amount=int(amount * 100),
                currency=wallet.currency.lower(),
                destination=wallet.stripe_connect_id,
                description=f"Payout for {request.user.email}"
            )
            
            with transaction.atomic():
                # Create payout request
                payout = PayoutRequest.objects.create(
                    wallet=wallet,
                    amount=amount,
                    status='PROCESSED',
                    processed_at=timezone.now()
                )
                # Deduct balance
                wallet.balance -= amount
                wallet.save()
                # Create transaction record
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=amount,
                    transaction_type='DEBIT',
                    description=f'Stripe Payout: {transfer.id}',
                    status='COMPLETED',
                    reference_id=transfer.id
                )
                
            log_audit_action(
                user=request.user,
                action='REQUEST_PAYOUT',
                resource_type='Wallet',
                resource_id=wallet.id,
                details={'amount': str(amount), 'transfer_id': transfer.id},
                request=request
            )
                
            return Response({'status': 'Payout successful', 'transfer_id': transfer.id, 'payout_id': payout.id})
            
        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': 'An unexpected error occurred during payout'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='onboard')
    def onboard(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        if not wallet.stripe_connect_id:
            account = stripe.Account.create(
                type='express',
                country='US',
                email=request.user.email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True},
                },
            )
            wallet.stripe_connect_id = account.id
            wallet.save()
            
        account_link = stripe.AccountLink.create(
            account=wallet.stripe_connect_id,
            refresh_url="https://example.com/reauth",
            return_url="https://example.com/return",
            type='account_onboarding',
        )
        
        return Response({
            'url': account_link.url,
            'created': account_link.created,
            'expires_at': account_link.expires_at,
        })

    @action(detail=False, methods=['get'], url_path='onboarding-status')
    def onboarding_status(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        if not wallet.stripe_connect_id:
            return Response({'is_onboarded': False})
            
        account = stripe.Account.retrieve(wallet.stripe_connect_id)
        is_onboarded = account.details_submitted
        return Response({'is_onboarded': is_onboarded})

    @action(detail=False, methods=['get'], url_path='stripe-dashboard')
    def stripe_dashboard(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        if not wallet.stripe_connect_id:
             return Response({
                 'error': 'No Stripe Connect account found. Please complete onboarding first.',
                 'needs_onboarding': True
             }, status=status.HTTP_404_NOT_FOUND)
            
        try:
            # Check if account has completed onboarding
            account = stripe.Account.retrieve(wallet.stripe_connect_id)
            
            if not account.details_submitted:
                print(f"DEBUG: Account {wallet.stripe_connect_id} has not completed onboarding")
                return Response({
                    'error': 'Please complete your Stripe Connect onboarding first.',
                    'needs_onboarding': True
                }, status=status.HTTP_400_BAD_REQUEST)
            
            print(f"DEBUG: Attempting to create login link for account: {wallet.stripe_connect_id}")
            login_link = stripe.Account.create_login_link(wallet.stripe_connect_id)
            print(f"DEBUG: Login link created successfully: {login_link.url}")
            return Response({'url': login_link.url})
        except stripe.error.StripeError as e:
            print(f"DEBUG: Stripe error occurred: {str(e)}")
            print(f"DEBUG: Error type: {type(e).__name__}")
            return Response({
                'error': f'Stripe error: {str(e)}',
                'needs_onboarding': 'onboarding' in str(e).lower()
            }, status=status.HTTP_400_BAD_REQUEST)


from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView

class StripeWebhookView(APIView):
    permission_classes = (permissions.AllowAny,)

    @method_decorator(csrf_exempt)
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            return Response({'error': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        # Handle the event
        # Note: Stripe is only used for appointment funding and background check payments.
        # Subscriptions are handled via native IAP (Apple/Google).
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            metadata = payment_intent.get('metadata', {})
            if metadata.get('type') == 'job_funding':
                appointment_id = metadata.get('appointment_id')
                if appointment_id:
                    from interactions.models import Appointment
                    try:
                        appointment = Appointment.objects.get(id=appointment_id)
                        appointment.is_funded = True
                        appointment.status = 'SCHEDULED' # Or another status if needed
                        appointment.save()
                        
                        # Also update the linked ServiceRequest
                        if appointment.service_request:
                            appointment.service_request.status = 'IN_PROGRESS'
                            appointment.service_request.save()
                            print(f"ServiceRequest {appointment.service_request.id} marked as IN_PROGRESS via webhook.")
                            
                        print(f"Appointment {appointment_id} marked as funded via webhook.")
                    except Appointment.DoesNotExist:
                        print(f"Appointment {appointment_id} not found for funding.")
                        
            elif metadata.get('type') == 'background_check':
                user_id = metadata.get('user_id')
                if user_id:
                    print(f"Background check payment succeeded for user {user_id}. Ready for Checkr initiation.")
                    # Frontend handles Checkr initiation using this payment intent ID, or we could trigger it here.
                    # We will rely on the frontend calling /initiate/ right after successful payment.

        return Response({'status': 'success'})


# ─── Apple In-App Purchase Receipt Validation ─────────────────────────────────

class AppleReceiptValidationView(APIView):
    """
    Called by the Flutter app after an iOS purchase succeeds.
    Validates the receipt against Apple's servers and activates the subscription.
    """
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)
    throttle_classes = [IAPReceiptThrottle]

    @method_decorator(csrf_exempt)
    def post(self, request):
        import requests as http_requests
        import json

        receipt_data = request.data.get('receipt_data')
        if not receipt_data:
            return Response({'error': 'receipt_data is required'}, status=status.HTTP_400_BAD_REQUEST)

        apple_shared_secret = getattr(settings, 'APPLE_SHARED_SECRET', '')
        payload = {'receipt-data': receipt_data, 'password': apple_shared_secret, 'exclude-old-transactions': True}

        # Try production first
        verify_url = 'https://buy.itunes.apple.com/verifyReceipt'
        resp = http_requests.post(verify_url, json=payload)
        data = resp.json()

        is_sandbox = False
        # If status 21007, it's a sandbox receipt, try sandbox URL
        if data.get('status') == 21007:
            verify_url = 'https://sandbox.itunes.apple.com/verifyReceipt'
            resp = http_requests.post(verify_url, json=payload)
            data = resp.json()
            is_sandbox = True
            
        apple_status = data.get('status', -1)
        if apple_status != 0:
            return Response(
                {'error': f'Apple receipt validation failed with status {apple_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract the most recent receipt info
        receipt_info = data.get('latest_receipt_info', [])
        if not receipt_info:
            receipt_info = data.get('receipt', {}).get('in_app', [])
        if not receipt_info:
            return Response({'error': 'No receipt info found in Apple response'}, status=status.HTTP_400_BAD_REQUEST)

        latest = sorted(receipt_info, key=lambda x: int(x.get('expires_date_ms', 0)), reverse=True)[0]
        original_transaction_id = latest.get('original_transaction_id')
        expires_ms = int(latest.get('expires_date_ms', 0))
        product_id = latest.get('product_id', '')

        # Activate the subscription in our DB
        subscription, _ = Subscription.objects.get_or_create(user=request.user)
        subscription.is_active = True
        subscription.is_sandbox = is_sandbox
        subscription.store_transaction_id = original_transaction_id  # Apple original_transaction_id

        # Look up by Apple product ID first, fall back to interval
        plan = SubscriptionPlan.objects.filter(apple_product_id=product_id, is_active=True).first()
        if not plan:
            interval = 'year' if 'yearly' in product_id.lower() else 'month'
            plan = SubscriptionPlan.objects.filter(interval=interval, is_active=True).first()
        else:
            interval = plan.interval

        if plan:
            subscription.plan = plan

        if expires_ms:
            subscription.next_payment = timezone.datetime.fromtimestamp(
                expires_ms / 1000.0, tz=timezone.utc
            )
        subscription.save()

        profile = Profile.objects.filter(user=request.user).first()
        if profile:
            profile.subscription_interval = interval
            profile.subscription_tier = plan.tier if plan else 'GOLD'
            profile.save()

        return Response({'status': 'active', 'expires_at': expires_ms})


# ─── Google Play Purchase Validation ─────────────────────────────────────────

class GooglePlayValidationView(APIView):
    """
    Called by the Flutter app after an Android purchase succeeds.
    Validates the purchase token against the Google Play Developer API.
    Requires GOOGLE_PLAY_SERVICE_ACCOUNT_JSON in Django settings.
    """
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)
    throttle_classes = [IAPReceiptThrottle]


    @method_decorator(csrf_exempt)
    def post(self, request):
        import json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        purchase_token = request.data.get('purchase_token')
        product_id = request.data.get('product_id')

        if not purchase_token or not product_id:
            return Response({'error': 'purchase_token and product_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        package_name = getattr(settings, 'ANDROID_PACKAGE_NAME', 'com.neighborservice.nsapp')
        service_account_json = getattr(settings, 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON', None)

        if not service_account_json:
            return Response({'error': 'Google Play service account not configured on server'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(service_account_json),
                scopes=['https://www.googleapis.com/auth/androidpublisher'],
            )
            service = build('androidpublisher', 'v3', credentials=credentials, cache_discovery=False)
            result = service.purchases().subscriptions().get(
                packageName=package_name,
                subscriptionId=product_id,
                token=purchase_token,
            ).execute()
        except Exception as e:
            return Response({'error': f'Google Play API error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        payment_state = result.get('paymentState')  # 1=received, 2=free trial
        expiry_ms = int(result.get('expiryTimeMillis', 0))

        if payment_state not in [1, 2]:
            return Response({'error': f'Payment not confirmed (state={payment_state})'}, status=status.HTTP_402_PAYMENT_REQUIRED)

        subscription, _ = Subscription.objects.get_or_create(user=request.user)
        subscription.is_active = True
        subscription.is_sandbox = (result.get('purchaseType') == 0) # 0 means test purchase
        subscription.store_transaction_id = purchase_token  # Google purchaseToken

        # Look up by Google product ID first, fall back to interval
        plan = SubscriptionPlan.objects.filter(google_product_id=product_id, is_active=True).first()
        if not plan:
            interval = 'year' if 'yearly' in product_id.lower() else 'month'
            plan = SubscriptionPlan.objects.filter(interval=interval, is_active=True).first()
        else:
            interval = plan.interval

        if plan:
            subscription.plan = plan

        if expiry_ms:
            subscription.next_payment = timezone.datetime.fromtimestamp(
                expiry_ms / 1000.0, tz=timezone.utc
            )
        subscription.save()

        profile = Profile.objects.filter(user=request.user).first()
        if profile:
            profile.subscription_interval = interval
            profile.subscription_tier = plan.tier if plan else 'GOLD'
            profile.save()

        return Response({'status': 'active', 'expires_at': expiry_ms})


# ─── Apple Server-to-Server (S2S) Notifications ───────────────────────────────

class AppleS2SNotificationView(APIView):
    """
    Apple calls this endpoint whenever a subscription status changes
    (renewal, cancellation, billing failure, etc.).
    Configure this URL in App Store Connect -> App -> Notifications.
    URL: https://[your-domain]/payments/webhook/apple-s2s/
    """
    permission_classes = (permissions.AllowAny,)

    @method_decorator(csrf_exempt)
    def post(self, request):
        payload = request.data
        notification_type = payload.get('notificationType') or payload.get('notification_type')
        unified_receipt = payload.get('unified_receipt', {})
        latest_receipt_info = unified_receipt.get('latest_receipt_info', [])

        if not latest_receipt_info:
            return Response({'status': 'ignored, no receipt info'})

        latest = sorted(latest_receipt_info, key=lambda x: int(x.get('expires_date_ms', 0)), reverse=True)[0]
        original_tx_id = latest.get('original_transaction_id')
        expires_ms = int(latest.get('expires_date_ms', 0))
        product_id = latest.get('product_id', '')

        sub = Subscription.objects.filter(store_transaction_id=original_tx_id).first()

        if notification_type in ['DID_RENEW', 'SUBSCRIBED', 'DID_RECOVER', 'INTERACTIVE_RENEWAL', 'OFFER_REDEEMED']:
            if sub:
                sub.is_active = True
                # Look up by Apple product ID first, fall back to interval
                plan = SubscriptionPlan.objects.filter(apple_product_id=product_id, is_active=True).first()
                if not plan:
                    interval = 'year' if 'yearly' in product_id.lower() else 'month'
                    plan = SubscriptionPlan.objects.filter(interval=interval, is_active=True).first()
                else:
                    interval = plan.interval

                if plan:
                    sub.plan = plan

                if expires_ms:
                    sub.next_payment = timezone.datetime.fromtimestamp(expires_ms / 1000.0, tz=timezone.utc)
                sub.save()
                profile = Profile.objects.filter(user=sub.user).first()
                if profile:
                    profile.subscription_interval = interval
                    profile.subscription_tier = plan.tier if plan else 'GOLD'
                    profile.save()

        elif notification_type in ['EXPIRED', 'DID_FAIL_TO_RENEW', 'REVOKE', 'CANCEL']:
            if sub:
                sub.is_active = False
                sub.save()
                profile = Profile.objects.filter(user=sub.user).first()
                if profile:
                    profile.subscription_tier = 'NONE'
                    profile.catalog_services.clear()
                    profile.service = ""
                    profile.save()

        return Response({'status': 'ok'})


# ─── Google Play Real-time Developer Notifications (Pub/Sub) ─────────────────

class GooglePubSubNotificationView(APIView):
    """
    Google sends subscription lifecycle events via Cloud Pub/Sub push subscriptions.
    Configure a Pub/Sub push endpoint in Google Cloud Console pointing here.
    URL: https://[your-domain]/payments/webhook/google-pubsub/
    Reference: https://developer.android.com/google/play/billing/rtdn-reference
    """
    permission_classes = (permissions.AllowAny,)

    # Google Pub/Sub notification types for subscriptions
    ACTIVE_TYPES = {1, 2, 4, 7}   # RENEWED, RECOVERED, RESTARTED, ON_HOLD_CANCELLED
    INACTIVE_TYPES = {3, 13}        # CANCELED, EXPIRED

    @method_decorator(csrf_exempt)
    def post(self, request):
        import base64
        import json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        try:
            message = request.data.get('message', {})
            data_b64 = message.get('data', '')
            decoded = base64.b64decode(data_b64).decode('utf-8')
            notification = json.loads(decoded)
        except Exception as e:
            return Response({'error': f'Failed to decode Pub/Sub message: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        sub_notification = notification.get('subscriptionNotification', {})
        notification_type = sub_notification.get('notificationType')
        purchase_token = sub_notification.get('purchaseToken')
        subscription_id = sub_notification.get('subscriptionId')
        package_name = notification.get('packageName')

        if not purchase_token:
            return Response({'status': 'ignored, no purchase token'})

        # Fetch fresh state from Google Play API
        service_account_json = getattr(settings, 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON', None)
        if service_account_json:
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(service_account_json),
                    scopes=['https://www.googleapis.com/auth/androidpublisher'],
                )
                service = build('androidpublisher', 'v3', credentials=credentials, cache_discovery=False)
                result = service.purchases().subscriptions().get(
                    packageName=package_name,
                    subscriptionId=subscription_id,
                    token=purchase_token,
                ).execute()
                expiry_ms = int(result.get('expiryTimeMillis', 0))
                payment_state = result.get('paymentState')
            except Exception as e:
                print(f'Google Pub/Sub: API error: {e}')
                expiry_ms = 0
                payment_state = None
        else:
            expiry_ms = 0
            payment_state = None

        sub = Subscription.objects.filter(store_transaction_id=purchase_token).first()

        if notification_type in self.ACTIVE_TYPES and payment_state in [1, 2]:
            if sub:
                sub.is_active = True
                # Look up by Google product ID first, fall back to interval
                plan = SubscriptionPlan.objects.filter(google_product_id=subscription_id, is_active=True).first()
                if not plan:
                    interval = 'year' if 'yearly' in subscription_id.lower() else 'month'
                    plan = SubscriptionPlan.objects.filter(interval=interval, is_active=True).first()

                if plan:
                    sub.plan = plan

                if expiry_ms:
                    sub.next_payment = timezone.datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc)
                sub.save()

        elif notification_type in self.INACTIVE_TYPES:
            if sub:
                sub.is_active = False
                sub.save()
                profile = Profile.objects.filter(user=sub.user).first()
                if profile:
                    profile.subscription_tier = 'NONE'
                    profile.catalog_services.clear()
                    profile.service = ""
                    profile.save()

        return Response({'status': 'ok'})
