from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Customer, Subscription, SubscriptionPlan, Wallet, PayoutRequest, WalletTransaction
from .serializers import (CustomerSerializer, SubscriptionSerializer, SubscriptionPlanSerializer,
                          WalletSerializer, WalletTransactionSerializer, PayoutRequestSerializer)
from django.db import transaction
from django.utils import timezone
import decimal
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

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
            appointment = Appointment.objects.get(id=appointment_id, seeker=request.user)
        except Appointment.DoesNotExist:
            return Response({'error': 'Appointment not found or not owned by you'}, status=status.HTTP_404_NOT_FOUND)
            
        customer, created = Customer.objects.get_or_create(user=request.user)
        
        if not customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=request.user.email)
            customer.stripe_customer_id = stripe_customer.id
            customer.save()
            
        ephemeral_key = stripe.EphemeralKey.create(
            customer=customer.stripe_customer_id,
            stripe_version='2022-11-15'
        )
        
        # Determine amount. If appointment has no price, expect it in request or use a default.
        # For now, we expect appointment to have some context or use request data.
        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount required'}, status=status.HTTP_400_BAD_REQUEST)
            
        payment_intent = stripe.PaymentIntent.create(
            amount=int(float(amount) * 100),
            currency='usd',
            customer=customer.stripe_customer_id,
            metadata={
                'appointment_id': str(appointment.id),
                'type': 'job_funding'
            },
            automatic_payment_methods={
                'enabled': True,
            },
        )
        
        # Store payment intent ID on appointment (pending confirmation)
        appointment.payment_intent_id = payment_intent.id
        appointment.save()
        
        return Response({
            'paymentIntent': payment_intent.client_secret,
            'ephemeralKey': ephemeral_key.secret,
            'customer': customer.stripe_customer_id,
            'publishableKey': settings.STRIPE_PUBLIC_KEY
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

    @action(detail=False, methods=['post'], url_path='montly/create')
    def monthly_create(self, request):
        # Frontend typo "montly" matched for compatibility
        plan = SubscriptionPlan.objects.filter(is_active=True).order_by('price').first()
        if not plan:
            return Response({'error': 'No active subscription plans found'}, status=status.HTTP_400_BAD_REQUEST)
            
        subscription, created = Subscription.objects.get_or_create(user=request.user)
        subscription.plan = plan
        subscription.is_active = True
        subscription.next_payment = timezone.now() + timezone.timedelta(days=30)
        subscription.save()
        
        return Response({"subscription": self.get_serializer(subscription).data})

    @action(detail=False, methods=['post'], url_path='create')
    def create_subscription(self, request):
        print(f"DEBUG: create_subscription data: {request.data}")
        plan_id = request.data.get('plan_id')
        if not plan_id:
            return Response({'error': 'Plan ID required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
            print(f"DEBUG: Plan found '{plan.name}', PriceID: {plan.stripe_price_id}")
            if not plan.stripe_price_id:
                 print("DEBUG: Missing Stripe Price ID")
                 return Response({'error': 'Plan has no Stripe Price ID'}, status=status.HTTP_400_BAD_REQUEST)
        except SubscriptionPlan.DoesNotExist:
             print("DEBUG: Plan not found or inactive")
             return Response({'error': 'Invalid or inactive plan'}, status=status.HTTP_400_BAD_REQUEST)

        # Get or Create Customer
        customer, _ = Customer.objects.get_or_create(user=request.user)
        if not customer.stripe_customer_id:
            try:
                print("DEBUG: Creating Stripe Customer...")
                stripe_customer = stripe.Customer.create(email=request.user.email)
                customer.stripe_customer_id = stripe_customer.id
                customer.save()
                print(f"DEBUG: Stripe Customer created: {customer.stripe_customer_id}")
            except Exception as e:
                print(f"DEBUG: Stripe Customer Error: {e}")
                return Response({'error': f'Stripe Customer Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Create Stripe Subscription
        try:
            print(f"DEBUG: Creating Subscription for Customer {customer.stripe_customer_id} Price {plan.stripe_price_id}")
            stripe_sub = stripe.Subscription.create(
                customer=customer.stripe_customer_id,
                items=[{'price': plan.stripe_price_id}],
                payment_behavior='default_incomplete',
                payment_settings={'save_default_payment_method': 'on_subscription'},
                expand=['latest_invoice.confirmation_secret'],
            )
            print(f"DEBUG: Stripe Subscription Created. Status: {stripe_sub.status}")
            
            subscription, created = Subscription.objects.get_or_create(user=request.user)
            subscription.plan = plan
            subscription.stripe_subscription_id = stripe_sub.id
            
            # If payment is successful/not required immediately (e.g. trial or stored card worked?)
            # Usually status is 'active' or 'incomplete'.
            if stripe_sub.status == 'active':
                subscription.is_active = True
                subscription.next_payment = timezone.datetime.fromtimestamp(stripe_sub.current_period_end)
            else:
                 # It's incomplete, waiting for payment. Frontend should handle client_secret if needed.
                 # For backward compatibility with current simple frontend, we might assume user has payment method.
                 # But if incomplete, we shouldn't mark as active yet? 
                 # The webhook will handle activation on 'invoice.payment_succeeded'.
                 subscription.is_active = False # Safest.
                 
            subscription.save()
            print("DEBUG: Local Subscription Saved")
            
            # Return necessary data for frontend to Complete Payment if needed
            response_data = {
                "subscription": self.get_serializer(subscription).data,
                "customer": customer.stripe_customer_id
            }

            # Generate Ephemeral Key
            try:
                ephemeral_key = stripe.EphemeralKey.create(
                    customer=customer.stripe_customer_id,
                    stripe_version='2022-11-15'
                )
                response_data['ephemeralKey'] = ephemeral_key.secret
            except Exception as e:
                print(f"Error creating ephemeral key: {e}")
            
            if stripe_sub.latest_invoice:
                if hasattr(stripe_sub.latest_invoice, 'confirmation_secret') and stripe_sub.latest_invoice.confirmation_secret:
                    response_data['client_secret'] = stripe_sub.latest_invoice.confirmation_secret.client_secret
                elif hasattr(stripe_sub.latest_invoice, 'payment_intent') and stripe_sub.latest_invoice.payment_intent:
                    # Fallback for older Stripe API versions if any
                    response_data['client_secret'] = stripe_sub.latest_invoice.payment_intent.client_secret
                  # Also helpful: publishableKey? frontend usually has it.
                 
            return Response(response_data)

        except stripe.error.StripeError as e:
            print(f"DEBUG: Stripe Subscription Error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='yearly/create')
    def yearly_create(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('-price')
        plan = plans.first()
        if not plan:
            return Response({'error': 'No active subscription plans found'}, status=status.HTTP_400_BAD_REQUEST)
            
        subscription, created = Subscription.objects.get_or_create(user=request.user)
        subscription.plan = plan
        subscription.is_active = True
        subscription.next_payment = timezone.now() + timezone.timedelta(days=365)
        subscription.save()
        
        return Response({"subscription": self.get_serializer(subscription).data})

    @action(detail=False, methods=['get'], url_path='user/get')
    def user_get(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        if not subscription:
            return Response({"subscription": None}, status=status.HTTP_200_OK)

        # Lazy Sync: Check Stripe if local status is inactive but we have a stripe_id
        if not subscription.is_active and subscription.stripe_subscription_id:
            try:
                print(f"DEBUG: Lazy Sync checking Stripe for sub {subscription.stripe_subscription_id}")
                stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                print(f"DEBUG: Stripe Subscription Status: {stripe_sub.status}")
                
                # Treat 'active' or 'trialing' as active locally
                if stripe_sub.status in ['active', 'trialing']:
                    subscription.is_active = True
                    subscription.next_payment = timezone.datetime.fromtimestamp(stripe_sub.current_period_end)
                    subscription.save()
                    print(f"DEBUG: Lazy Sync updated subscription to ACTIVE (Status: {stripe_sub.status})")
                elif stripe_sub.status == 'incomplete':
                    # Check the latest invoice for payment
                    if stripe_sub.latest_invoice:
                        invoice = stripe.Invoice.retrieve(stripe_sub.latest_invoice)
                        if invoice.status == 'paid':
                             subscription.is_active = True
                             subscription.next_payment = timezone.datetime.fromtimestamp(stripe_sub.current_period_end)
                             subscription.save()
                             print("DEBUG: Lazy Sync updated subscription to ACTIVE (Found PAID invoice)")
            except Exception as e:
                print(f"DEBUG: Lazy Sync failed: {e}")

        serializer = self.get_serializer(subscription)
        return Response({"subscription": serializer.data})

    @action(detail=False, methods=['delete'], url_path='user/delete')
    def user_delete(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        if subscription:
            subscription.delete()
            return Response({"message": "Subscription deleted"}, status=status.HTTP_200_OK)
        return Response({"message": "No subscription found"}, status=status.HTTP_404_NOT_FOUND)

class WalletViewSet(viewsets.ModelViewSet):
    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

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
        if event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            subscription_id = invoice.get('subscription')
            
            if subscription_id:
                try:
                    # Find subscription by stripe_subscription_id
                    subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
                    
                    # Update status
                    subscription.is_active = True
                    
                    # Update next payment date if available from invoice lines or period_end
                    if invoice.get('lines') and invoice['lines'].get('data'):
                        period_end = invoice['lines']['data'][0]['period']['end']
                        subscription.next_payment = timezone.datetime.fromtimestamp(period_end)
                    
                    subscription.save()
                    print(f"Updated subscription {subscription.id} for invoice payment success.")
                    
                except Subscription.DoesNotExist:
                    print(f"Subscription not found for ID: {subscription_id}")
                    
        elif event['type'] == 'customer.subscription.deleted':
            subscription_data = event['data']['object']
            subscription_id = subscription_data.get('id')
            
            if subscription_id:
                try:
                    subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
                    subscription.is_active = False
                    subscription.save()
                    print(f"Deactivated subscription {subscription.id} due to deletion.")
                except Subscription.DoesNotExist:
                    print(f"Subscription not found for ID: {subscription_id}")

        elif event['type'] == 'payment_intent.succeeded':
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

        return Response({'status': 'success'})
