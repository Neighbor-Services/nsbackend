from rest_framework import serializers
from .models import Customer, Subscription, SubscriptionPlan, Wallet, WalletTransaction, PayoutRequest

class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = '__all__'

class PayoutRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutRequest
        fields = '__all__'
        read_only_fields = ('wallet', 'status', 'processed_at', 'admin_notes')

class WalletSerializer(serializers.ModelSerializer):
    transactions = WalletTransactionSerializer(many=True, read_only=True)
    payout_requests = PayoutRequestSerializer(many=True, read_only=True)

    class Meta:
        model = Wallet
        fields = ('id', 'user', 'balance', 'currency', 'stripe_connect_id', 'transactions', 'payout_requests')
        read_only_fields = ('user', 'balance', 'currency')

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ('user',)

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plans"""
    formatted_price = serializers.ReadOnlyField()
    
    class Meta:
        model = SubscriptionPlan
        fields = ('id', 'name', 'tier', 'interval', 'description', 'price', 'currency', 'formatted_price', 
                  'features', 'is_active', 'display_order', 'stripe_price_id', 
                  'stripe_product_id', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

class SubscriptionSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source='plan', read_only=True)
    plan_price = serializers.ReadOnlyField()
    
    class Meta:
        model = Subscription
        fields = ('id', 'user', 'plan', 'plan_details', 'plan_price', 
                  'stripe_subscription_id', 'stripe_plan_id', 'next_payment', 
                  'is_active', 'created_at', 'updated_at')
        read_only_fields = ('user', 'created_at', 'updated_at')
