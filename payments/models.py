from django.db import models
from django.conf import settings
import uuid
from encrypted_model_fields.fields import EncryptedCharField
from psqlextra.models import PostgresPartitionedModel
from psqlextra.types import PostgresPartitioningMethod

class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='customer')
    stripe_customer_id = EncryptedCharField(max_length=255, blank=True, null=True)
    stripe_account_id = EncryptedCharField(max_length=255, blank=True, null=True)
    default_payment_method = EncryptedCharField(max_length=255, blank=True, null=True)
    ephemeral_secret = EncryptedCharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stripe Customer: {self.user.email}"

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, default='USD')
    stripe_connect_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet for {self.user.email} - {self.balance}"

class WalletTransaction(PostgresPartitionedModel):
    TRANSACTION_TYPES = (
        ('CREDIT', 'Credit'),
        ('DEBIT', 'Debit'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED')
    reference_id = models.CharField(max_length=100, blank=True, null=True) # E.g., Appointment ID or Stripe Payout ID
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
        ]

    class PartitioningMeta:
        method = PostgresPartitioningMethod.RANGE
        key = ["created_at"]

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} - {self.wallet.user.email}"

class PayoutRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSED', 'Processed'),
        ('REJECTED', 'Rejected'),
    )
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='payout_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payout {self.amount} - {self.wallet.user.email} - {self.status}"

class SubscriptionPlan(models.Model):
    """Subscription plan with adjustable pricing"""
    TIERS = (
        ('FREE', 'Free'),
        ('SILVER', 'Silver'),
        ('GOLD', 'Gold'),
        ('PLATINUM', 'Platinum'),
    )
    INTERVAL_CHOICES = (
        ('month', 'Monthly'),
        ('year', 'Yearly'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, help_text="Plan name (e.g., Basic, Premium, Enterprise)")
    tier = models.CharField(max_length=10, choices=TIERS, default='FREE')
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='month')
    description = models.TextField(blank=True, help_text="Detailed plan description")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Monthly price")
    currency = models.CharField(max_length=3, default='USD', help_text="Currency code")
    features = models.JSONField(default=list, blank=True, help_text="List of plan features")
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Price ID")
    stripe_product_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Product ID")
    is_active = models.BooleanField(default=True, help_text="Is this plan available for purchase?")
    display_order = models.IntegerField(default=0, help_text="Display order (lower numbers first)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'price']
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'

    def __str__(self):
        return f"{self.name} - {self.currency} {self.price}/{self.interval}"

    def save(self, *args, **kwargs):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        if not self.stripe_product_id:
            try:
                product = stripe.Product.create(
                    name=self.name,
                    description=self.description or f"{self.name} Subscription Plan"
                )
                self.stripe_product_id = product.id
            except Exception as e:
                print(f"Error creating Stripe Product: {e}")

        # Check if price changed or if stripe_price_id is missing.
        # Ideally, we should check if self.pk exists (update) and if price changed.
        # But for simplicity, we create a price if stripe_price_id is missing.
        # If user updates price in Admin, we *should* create a new Stripe Price,
        # but that requires knowing the old value.
        # For now, we only handle creation if missing.
        
        if self.stripe_product_id and not self.stripe_price_id:
            try:
                price = stripe.Price.create(
                    product=self.stripe_product_id,
                    unit_amount=int(self.price * 100),
                    currency=self.currency.lower(),
                    recurring={"interval": self.interval},
                )
                self.stripe_price_id = price.id
            except Exception as e:
                print(f"Error creating Stripe Price: {e}")

        # If price was updated (detected by dirty field or similar logic),
        # we would ideally archive the old price and create a new one.
        # Here we just ensure we have *a* price.
        
        super().save(*args, **kwargs)

    def formatted_price(self):
        """Return formatted price with currency symbol"""
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
        }
        symbol = currency_symbols.get(self.currency, self.currency)
        return f"{symbol}{self.price}"

class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions', help_text="Subscription plan")
    stripe_subscription_id = EncryptedCharField(max_length=255, blank=True, null=True)
    stripe_plan_id = models.CharField(max_length=100, blank=True, null=True)  # Deprecated, use plan.stripe_price_id
    next_payment = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        plan_name = self.plan.name if self.plan else "No Plan"
        return f"Subscription for {self.user.email} - {plan_name}"

    @property
    def plan_price(self):
        """Return the plan price if available"""
        return self.plan.formatted_price if self.plan else "N/A"
