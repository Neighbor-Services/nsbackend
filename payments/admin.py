from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Sum
from unfold.admin import ModelAdmin
from unfold.decorators import display
from .models import Customer, Subscription, SubscriptionPlan, Wallet, WalletTransaction, PayoutRequest

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ModelAdmin):
    list_display = ('name', 'tier', 'interval', 'display_formatted_price', 'currency', 'display_status', 'display_order', 'subscriber_count', 'updated_at')
    list_filter = ('is_active', 'currency', 'created_at')
    search_fields = ('name', 'description')
    list_editable = ('display_order',)
    ordering = ('display_order', 'price')
    
    fieldsets = (
        ('Plan Details', {
            'fields': ('name', 'tier', 'description', 'display_order')
        }),
        ('Pricing', {
            'fields': (('price', 'currency', 'interval'), 'is_active'),
            'classes': ('wide',)
        }),
        ('Features', {
            'fields': ('features',),
            'description': 'Enter plan features as a JSON list, e.g., ["Feature 1", "Feature 2"]'
        }),
        ('Stripe Integration', {
            'fields': ('stripe_price_id', 'stripe_product_id'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    @display(description='Price', ordering='price')
    def display_formatted_price(self, obj):
        """Display formatted price with currency symbol"""
        return format_html(
            '<span style="font-weight: bold; color: #10b981;">{}</span>',
            obj.formatted_price
        )
    
    @display(description='Status', ordering='is_active', boolean=True)
    def display_status(self, obj):
        """Display active status with color indicator"""
        return obj.is_active
    
    @display(description='Subscribers')
    def subscriber_count(self, obj):
        """Display number of active subscribers"""
        count = obj.subscriptions.filter(is_active=True).count()
        return format_html(
            '<span style="background: #3b82f6; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            count
        )
    
    actions = ['activate_plans', 'deactivate_plans']
    
    @admin.action(description='Activate selected plans')
    def activate_plans(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} plan(s) activated successfully.')
    
    @admin.action(description='Deactivate selected plans')
    def deactivate_plans(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} plan(s) deactivated successfully.')

@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ('user_email', 'plan_name', 'display_plan_price', 'display_status', 'next_payment', 'created_at')
    list_filter = ('is_active', 'plan', 'created_at')
    search_fields = ('user__email', 'stripe_subscription_id')
    autocomplete_fields = ['user', 'plan']
    
    fieldsets = (
        ('Subscription Details', {
            'fields': ('user', 'plan', 'is_active')
        }),
        ('Payment Information', {
            'fields': ('next_payment',)
        }),
        ('Stripe Details', {
            'fields': ('stripe_subscription_id', 'stripe_plan_id'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    @display(description='User', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email
    
    @display(description='Plan', ordering='plan__name')
    def plan_name(self, obj):
        if obj.plan:
            return format_html(
                '<span style="font-weight: 600;">{}</span>',
                obj.plan.name
            )
        return format_html('<span style="color: #6b7280;">No Plan</span>')
    
    @display(description='Price')
    def display_plan_price(self, obj):
        if obj.plan:
            return format_html(
                '<span style="color: #10b981; font-weight: bold;">{}</span>',
                obj.plan.formatted_price
            )
        return '-'
    
    @display(description='Active', ordering='is_active', boolean=True)
    def display_status(self, obj):
        return obj.is_active
    
    actions = ['activate_subscriptions', 'deactivate_subscriptions']
    
    @admin.action(description='Activate selected subscriptions')
    def activate_subscriptions(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} subscription(s) activated successfully.')
    
    @admin.action(description='Deactivate selected subscriptions')
    def deactivate_subscriptions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} subscription(s) deactivated successfully.')

@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_display = ('user_email', 'has_stripe_customer', 'has_stripe_account', 'created_at')
    search_fields = ('user__email',)
    autocomplete_fields = ['user']
    
    @display(description='User', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email
    
    @display(description='Stripe Customer', boolean=True)
    def has_stripe_customer(self, obj):
        return bool(obj.stripe_customer_id)
    
    @display(description='Stripe Account', boolean=True)
    def has_stripe_account(self, obj):
        return bool(obj.stripe_account_id)

@admin.register(Wallet)
class WalletAdmin(ModelAdmin):
    list_display = ('user_email', 'display_balance', 'currency', 'transaction_count', 'updated_at')
    search_fields = ('user__email',)
    list_filter = ('currency', 'created_at')
    autocomplete_fields = ['user']
    
    @display(description='User', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email
    
    @display(description='Balance', ordering='balance')
    def display_balance(self, obj):
        """Display balance with color coding"""
        color = '#10b981' if obj.balance >= 0 else '#ef4444'
        return format_html(
            '<span style="font-weight: bold; color: {};">{} {}</span>',
            color,
            obj.currency,
            obj.balance
        )
    
    @display(description='Transactions')
    def transaction_count(self, obj):
        count = obj.transactions.count()
        return format_html(
            '<span style="background: #6366f1; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            count
        )

@admin.register(WalletTransaction)
class WalletTransactionAdmin(ModelAdmin):
    list_display = ('wallet_user', 'display_amount', 'transaction_type', 'display_status', 'description', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('wallet__user__email', 'description', 'reference_id')
    autocomplete_fields = ['wallet']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('wallet', 'status')
        }),
        ('Amount & Type', {
            'fields': (('amount', 'transaction_type'), 'description', 'reference_id')
        }),
    )
    
    @display(description='User', ordering='wallet__user__email')
    def wallet_user(self, obj):
        return obj.wallet.user.email
    
    @display(description='Amount', ordering='amount')
    def display_amount(self, obj):
        """Display amount with color coding based on type"""
        color = '#10b981' if obj.transaction_type == 'CREDIT' else '#ef4444'
        prefix = '+' if obj.transaction_type == 'CREDIT' else '-'
        return format_html(
            '<span style="font-weight: bold; color: {};">{}{}</span>',
            color,
            prefix,
            obj.amount
        )
    
    @display(description='Status', ordering='status')
    def display_status(self, obj):
        """Display status with color coding"""
        colors = {
            'PENDING': '#f59e0b',
            'COMPLETED': '#10b981',
            'FAILED': '#ef4444',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#6b7280'),
            obj.status
        )

@admin.register(PayoutRequest)
class PayoutRequestAdmin(ModelAdmin):
    list_display = ('wallet_user', 'display_amount', 'display_status', 'created_at', 'processed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('wallet__user__email',)
    autocomplete_fields = ['wallet']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Payout Details', {
            'fields': ('wallet', 'amount', 'status')
        }),
        ('Admin Notes', {
            'fields': ('admin_notes',),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at',)
    
    @display(description='User', ordering='wallet__user__email')
    def wallet_user(self, obj):
        return obj.wallet.user.email
    
    @display(description='Amount', ordering='amount')
    def display_amount(self, obj):
        return format_html(
            '<span style="font-weight: bold; color: #10b981;">${}</span>',
            obj.amount
        )
    
    @display(description='Status', ordering='status')
    def display_status(self, obj):
        """Display status with color coding"""
        colors = {
            'PENDING': '#f59e0b',
            'PROCESSED': '#10b981',
            'REJECTED': '#ef4444',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            colors.get(obj.status, '#6b7280'),
            obj.status
        )
    
    actions = ['approve_payouts', 'reject_payouts']
    
    @admin.action(description='Approve selected payout requests')
    def approve_payouts(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='PENDING').update(
            status='PROCESSED',
            processed_at=timezone.now()
        )
        self.message_user(request, f'{updated} payout(s) approved successfully.')
    
    @admin.action(description='Reject selected payout requests')
    def reject_payouts(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='PENDING').update(
            status='REJECTED',
            processed_at=timezone.now()
        )
        self.message_user(request, f'{updated} payout(s) rejected.')
