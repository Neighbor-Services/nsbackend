from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, SubscriptionViewSet, SubscriptionPlanViewSet, WalletViewSet, StripeWebhookView

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'subscription-plans', SubscriptionPlanViewSet, basename='subscription-plan')
router.register(r'wallet', WalletViewSet, basename='wallet')

urlpatterns = [
    path('webhook/', StripeWebhookView.as_view(), name='stripe_webhook'),
    
    # Customer specific paths
    path('user/', CustomerViewSet.as_view({'get': 'user'}), name='customer-user'),
    path('create/', CustomerViewSet.as_view({'post': 'create'}), name='customer-create'),
    path('ephmeral/', CustomerViewSet.as_view({'patch': 'ephmeral'}), name='customer-ephemeral'),
    path('paymentmethod/update/', CustomerViewSet.as_view({'patch': 'update_payment_method'}), name='customer-payment-method-update'),
    path('account/connect/', CustomerViewSet.as_view({'post': 'account_connect'}), name='customer-account-connect'),
    path('transfer/', CustomerViewSet.as_view({'post': 'transfer'}), name='customer-transfer'),
    path('fund-appointment/', CustomerViewSet.as_view({'post': 'fund_appointment'}), name='customer-fund-appointment'),
    path('payment-sheet/', CustomerViewSet.as_view({'post': 'payment_sheet'}), name='customer-payment-sheet'),
    
    # Subscription specific paths
    path('montly/create/', SubscriptionViewSet.as_view({'post': 'monthly_create'}), name='subscription-monthly-create'),
    path('yearly/create/', SubscriptionViewSet.as_view({'post': 'yearly_create'}), name='subscription-yearly-create'),
    path('user/get/', SubscriptionViewSet.as_view({'get': 'user_get'}), name='subscription-user-get'),
    path('user/delete/', SubscriptionViewSet.as_view({'delete': 'user_delete'}), name='subscription-user-delete'),
    path('subscription/create/', SubscriptionViewSet.as_view({'post': 'create_subscription'}), name='subscription-create'),

    path('', include(router.urls)),
]
