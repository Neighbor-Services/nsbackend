from django.db import models
from django.conf import settings
import uuid


class Report(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('REVIEWING', 'Reviewing'),
        ('RESOLVED', 'Resolved'),
        ('DISMISSED', 'Dismissed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports_sent')
    reported_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports_received', null=True, blank=True)
    resource_type = models.CharField(max_length=100) # Message, Review, ServiceRequest
    resource_id = models.CharField(max_length=100)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Report by {self.reporter.email} on {self.resource_type}: {self.id}"
class ProviderVerification(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='verification_requests')
    document_front = models.ImageField(upload_to='verifications/')
    document_back = models.ImageField(upload_to='verifications/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    reviewer_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Verification for {self.provider.email} - {self.status}"


class BackgroundCheck(models.Model):
    """
    Tracks a Checkr.com background check for a provider.

    Flow:
        1. Backend creates a Checkr candidate + invitation → stores IDs here.
        2. Provider completes their info on Checkr's hosted form (invitation_url).
        3. Checkr fires a webhook → status + result updated here.
        4. On CLEAR, Profile.is_identity_verified is set to True automatically.
    """

    STATUS_PENDING = 'PENDING'
    STATUS_CLEAR = 'CLEAR'
    STATUS_CONSIDER = 'CONSIDER'
    STATUS_SUSPENDED = 'SUSPENDED'
    STATUS_DISPUTE = 'DISPUTE'
    STATUS_CANCELED = 'CANCELED'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_CLEAR, 'Clear'),
        (STATUS_CONSIDER, 'Consider'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_DISPUTE, 'Dispute'),
        (STATUS_CANCELED, 'Canceled'),
    )

    ADJUDICATION_ENGAGED = 'ENGAGED'
    ADJUDICATION_PRE_ADVERSE = 'PRE_ADVERSE_ACTION'
    ADJUDICATION_ADVERSE = 'ADVERSE_ACTION'

    ADJUDICATION_CHOICES = (
        (ADJUDICATION_ENGAGED, 'Engaged'),
        (ADJUDICATION_PRE_ADVERSE, 'Pre-Adverse Action'),
        (ADJUDICATION_ADVERSE, 'Adverse Action'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='background_checks',
    )

    # Checkr identifiers
    checkr_candidate_id = models.CharField(max_length=255, blank=True, null=True)
    checkr_report_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    checkr_invitation_id = models.CharField(max_length=255, blank=True, null=True)

    # Provider-facing invitation link (Checkr-hosted form)
    invitation_url = models.URLField(max_length=1024, blank=True, null=True)

    # Background check package used (e.g. tasker_standard)
    package = models.CharField(max_length=100, default='tasker_standard')

    # Overall status mirroring Checkr report status
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    # Adjudication outcome (set by Checkr or admin)
    adjudication = models.CharField(max_length=30, choices=ADJUDICATION_CHOICES, blank=True, null=True)

    # Full Checkr report JSON stored for audit purposes
    result = models.JSONField(blank=True, null=True)

    # Sync tracking
    last_synced_at = models.DateTimeField(blank=True, null=True)
    sync_attempt_count = models.PositiveSmallIntegerField(default=0)

    # Admin / internal notes
    notes = models.TextField(blank=True, null=True)
    
    # Stripe payment tracking
    payment_intent_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Background Check'
        verbose_name_plural = 'Background Checks'
        indexes = [
            models.Index(fields=['provider', 'status']),
        ]

    def __str__(self):
        return f"BackgroundCheck [{self.status}] for {self.provider.email}"

    @property
    def is_clear(self):
        return self.status == self.STATUS_CLEAR

    @property
    def is_terminal(self):
        """Returns True if no further status changes are expected."""
        return self.status in (
            self.STATUS_CLEAR,
            self.STATUS_CONSIDER,
            self.STATUS_SUSPENDED,
            self.STATUS_CANCELED,
        )

class ModerationSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    PAYMENT_MODE_CHOICES = (
        ('IN_APP_STRIPE', 'In-App Stripe Checkout'),
        ('NATIVE_CHECKR', 'Native Checkr Candidate-Paid'),
    )
    background_check_payment_mode = models.CharField(
        max_length=20, 
        choices=PAYMENT_MODE_CHOICES, 
        default='IN_APP_STRIPE',
        help_text="Choose how providers pay for their background check."
    )
    background_check_fee = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=29.99,
        help_text="The fee charged to providers for the background check (used for In-App Stripe Checkout)."
    )
    
    class Meta:
        verbose_name = "Moderation Setting"
        verbose_name_plural = "Moderation Settings"

    def __str__(self):
        return "Global Moderation Settings"
