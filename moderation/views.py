import json
import logging

from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Report, ProviderVerification, BackgroundCheck, ModerationSetting
from .serializers import (
    ReportSerializer,
    ProviderVerificationSerializer,
    BackgroundCheckSerializer,
)
from . import checkr_client
from .checkr_client import CheckrAPIError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Existing viewsets (unchanged)
# ---------------------------------------------------------------------------

class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class ProviderVerificationViewSet(viewsets.ModelViewSet):
    queryset = ProviderVerification.objects.all()
    serializer_class = ProviderVerificationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(provider=self.request.user)

    def perform_create(self, serializer):
        serializer.save(provider=self.request.user)


# ---------------------------------------------------------------------------
# Background Check ViewSet
# ---------------------------------------------------------------------------

class IsProvider(permissions.BasePermission):
    """Only providers may initiate background checks."""
    message = "Only providers can initiate a background check."

    def has_permission(self, request, view):
        # Allow staff to read all
        if request.user.is_staff:
            return True
        try:
            return request.user.profile.user_type == 'PROVIDER'
        except Exception:
            return False


class BackgroundCheckViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Background check lifecycle for providers.

    POST   /api/v1/moderation/background-checks/initiate/
           → Creates Checkr candidate + invitation, returns `invitation_url`.

    GET    /api/v1/moderation/background-checks/
           → Lists own background checks (staff sees all).

    POST   /api/v1/moderation/background-checks/{id}/resync/
           → Forces a manual pull from Checkr (staff only).
    """

    serializer_class = BackgroundCheckSerializer
    permission_classes = [permissions.IsAuthenticated, IsProvider]

    def get_queryset(self):
        if self.request.user.is_staff:
            return BackgroundCheck.objects.select_related('provider').all()
        return BackgroundCheck.objects.filter(provider=self.request.user)

    # ------------------------------------------------------------------
    # GET /background-checks/config/
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='config', permission_classes=[permissions.AllowAny])
    def config(self, request):
        """
        Returns the global background check configuration.
        """
        setting = ModerationSetting.objects.first()
        payment_mode = setting.background_check_payment_mode if setting else 'IN_APP_STRIPE'
        return Response({'payment_mode': payment_mode})

    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='initiate')
    def initiate(self, request):
        """
        Initiate a Checkr background check for the authenticated provider.

        Prevents duplicate active checks (only one PENDING check allowed).
        Returns { id, invitation_url, status }.
        """
        try:
            user = request.user

            # Guard: only one active check at a time
            existing = BackgroundCheck.objects.filter(
                provider=user,
                status=BackgroundCheck.STATUS_PENDING,
            ).first()
            if existing:
                return Response(
                    {
                        'detail': 'You already have a pending background check.',
                        'invitation_url': existing.invitation_url,
                        'id': str(existing.id),
                        'status': existing.status,
                    },
                    status=status.HTTP_200_OK,
                )

            # Check global setting
            setting = ModerationSetting.objects.first()
            payment_mode = setting.background_check_payment_mode if setting else 'IN_APP_STRIPE'

            payment_intent_id = request.data.get('payment_intent_id')

            if payment_mode == 'IN_APP_STRIPE':
                # Require payment intent
                if not payment_intent_id:
                     return Response(
                         {'detail': 'A valid payment_intent_id is required to initiate a background check.'},
                         status=status.HTTP_400_BAD_REQUEST,
                     )

                # Verify payment intent with Stripe
                import stripe
                try:
                     stripe.api_key = settings.STRIPE_SECRET_KEY
                     intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                     if intent.status != 'succeeded':
                         return Response(
                             {'detail': f'Payment intent status is {intent.status}. Expected "succeeded".'},
                             status=status.HTTP_400_BAD_REQUEST,
                         )
                     if intent.metadata.get('type') != 'background_check' or intent.metadata.get('user_id') != str(user.id):
                         return Response(
                             {'detail': 'Payment intent is not valid for this background check.'},
                             status=status.HTTP_400_BAD_REQUEST,
                         )
                except Exception as e:
                     logger.error("Stripe verification error in background check initiate: %s", e)
                     return Response(
                         {'detail': f'Payment verification failed: {str(e)}'},
                         status=status.HTTP_400_BAD_REQUEST,
                     )

                # Ensure payment intent hasn't already been used
                if BackgroundCheck.objects.filter(payment_intent_id=payment_intent_id).exists():
                     return Response(
                         {'detail': 'This payment has already been used for a background check.'},
                         status=status.HTTP_400_BAD_REQUEST,
                     )

            # Validate provider has enough profile data
            try:
                profile = user.profile
            except Exception:
                return Response(
                    {'detail': 'Provider profile not found.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not profile.state and not profile.zip_code:
                return Response(
                    {
                        'detail': (
                            'Your profile must have a state or zip code set '
                            'before initiating a background check.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Build work location for Checkr
            work_location = {}
            # if profile.state:
            #     work_location['state'] = profile.state
            # if profile.city:
            #     work_location['city'] = profile.city
            # if profile.zip_code:
            #     work_location['zipcode'] = profile.zip_code
            if profile.country:
                work_location['country'] = 'US'

            package = getattr(settings, 'CHECKR_PACKAGE', 'tasker_standard')

            try:
                # 1. Create Checkr candidate
                candidate = checkr_client.create_candidate(profile)
                candidate_id = candidate['id']

                # 2. Create invitation (Checkr-hosted form flow)
                invitation = checkr_client.create_invitation(
                    candidate_id=candidate_id,
                    package=package,
                    work_location=work_location,
                )
            except CheckrAPIError as exc:
                logger.error("Checkr API error during initiation for user %s: %s", user.email, exc)
                return Response(
                    {'detail': f'Background check initiation failed: {str(exc)}'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # 3. Persist BackgroundCheck record
            bc = BackgroundCheck.objects.create(
                provider=user,
                checkr_candidate_id=candidate_id,
                checkr_invitation_id=invitation.get('id'),
                invitation_url=invitation.get('invitation_url'),
                package=package,
                status=BackgroundCheck.STATUS_PENDING,
                payment_intent_id=payment_intent_id,
            )

            logger.info(
                "BackgroundCheck %s created for provider %s (invitation=%s)",
                bc.id, user.email, bc.checkr_invitation_id,
            )

            serializer = self.get_serializer(bc)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.exception("Unexpected error in background check initiate:")
            return Response(
                {'detail': f'Internal server error: {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ------------------------------------------------------------------
    # POST /background-checks/{id}/resync/  (staff only)
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='resync',
            permission_classes=[permissions.IsAdminUser])
    def resync(self, request, pk=None):
        """
        Manually re-pull the Checkr report for this background check.
        Staff-only. Useful when a webhook was missed.
        """
        bc = self.get_object()

        if not bc.checkr_report_id:
            return Response(
                {'detail': 'No Checkr report ID on record yet. The provider may not have completed the invitation form.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = checkr_client.get_report(bc.checkr_report_id)
        except CheckrAPIError as exc:
            return Response(
                {'detail': f'Checkr sync failed: {str(exc)}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        _apply_report_to_background_check(bc, report)

        serializer = self.get_serializer(bc)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def checkr_webhook_view(request):
    """
    Receives Checkr webhook events.

    Verified via HMAC-SHA256 signature in X-Checkr-Signature header.
    Handles:
        - report.completed
        - report.pre_adverse_action
        - report.adverse_action
        - report.suspended
        - report.canceled
        - report.disputed

    All other event types are acknowledged (200) and ignored.
    """
    # 1. Signature verification
    signature = request.headers.get('X-Checkr-Signature', '')
    if not checkr_client.verify_webhook_signature(request.body, signature):
        logger.warning("Checkr webhook received with invalid signature.")
        return JsonResponse({'detail': 'Invalid signature.'}, status=401)

    # 2. Parse payload
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Checkr webhook received non-JSON payload.")
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)

    event_type = payload.get('type', '')
    data = payload.get('data', {}).get('object', {})

    logger.info("Checkr webhook received: type=%s", event_type)

    # Only process report-level events
    if not event_type.startswith('report.'):
        return JsonResponse({'detail': 'Acknowledged.'}, status=200)

    report_id = data.get('id')
    if not report_id:
        logger.warning("Checkr webhook missing report ID in payload.")
        return JsonResponse({'detail': 'Missing report ID.'}, status=400)

    # 3. Look up BackgroundCheck by report ID
    bc = BackgroundCheck.objects.filter(checkr_report_id=report_id).first()

    if bc is None:
        # The report ID might not be stored yet (first webhook for an invitation).
        # Try to match via candidate_id.
        candidate_id = data.get('candidate_id')
        if candidate_id:
            bc = BackgroundCheck.objects.filter(
                checkr_candidate_id=candidate_id,
                status=BackgroundCheck.STATUS_PENDING,
            ).first()

    if bc is None:
        logger.warning(
            "Checkr webhook: no BackgroundCheck found for report_id=%s", report_id
        )
        # Return 200 so Checkr doesn't keep retrying for orphaned reports
        return JsonResponse({'detail': 'No matching record found — acknowledged.'}, status=200)

    # 4. Apply the report data
    _apply_report_to_background_check(bc, data)

    return JsonResponse({'detail': 'OK.'}, status=200)


# ---------------------------------------------------------------------------
# Shared helper — apply Checkr report data to a BackgroundCheck
# ---------------------------------------------------------------------------

def _apply_report_to_background_check(bc: BackgroundCheck, report: dict):
    """
    Update a BackgroundCheck (and related Profile) from a Checkr report dict.
    Called by both the webhook handler and the resync action.
    """
    report_id = report.get('id')
    checkr_status = (report.get('status') or '').upper()
    adjudication = report.get('adjudication')

    # Map Checkr status strings to our model choices
    status_map = {
        'CLEAR': BackgroundCheck.STATUS_CLEAR,
        'CONSIDER': BackgroundCheck.STATUS_CONSIDER,
        'SUSPENDED': BackgroundCheck.STATUS_SUSPENDED,
        'DISPUTE': BackgroundCheck.STATUS_DISPUTE,
        'CANCELED': BackgroundCheck.STATUS_CANCELED,
        'PENDING': BackgroundCheck.STATUS_PENDING,
        # Checkr may also send 'complete' before processing is final
        'COMPLETE': BackgroundCheck.STATUS_CLEAR,
    }
    mapped_status = status_map.get(checkr_status, BackgroundCheck.STATUS_PENDING)

    # Map adjudication
    adj_map = {
        'engaged': BackgroundCheck.ADJUDICATION_ENGAGED,
        'pre_adverse_action': BackgroundCheck.ADJUDICATION_PRE_ADVERSE,
        'adverse_action': BackgroundCheck.ADJUDICATION_ADVERSE,
    }
    mapped_adjudication = adj_map.get((adjudication or '').lower())

    bc.checkr_report_id = report_id or bc.checkr_report_id
    bc.status = mapped_status
    bc.adjudication = mapped_adjudication
    bc.result = report
    bc.last_synced_at = timezone.now()
    bc.sync_attempt_count += 1
    bc.save()

    logger.info(
        "BackgroundCheck %s updated: status=%s adjudication=%s",
        bc.id, bc.status, bc.adjudication,
    )

    # Update provider profile identity verification flag
    _sync_provider_identity(bc)

    # Send push notification to provider
    _notify_provider(bc)


def _sync_provider_identity(bc: BackgroundCheck):
    """
    Set Profile.is_identity_verified based on background check outcome.

    CLEAR     → True
    CONSIDER / ADVERSE / SUSPENDED / CANCELED  → False (or leave as-is)
    """
    try:
        profile = bc.provider.profile
    except Exception:
        logger.warning("Could not resolve profile for provider %s", bc.provider_id)
        return

    if bc.is_clear:
        if not profile.is_identity_verified:
            profile.is_identity_verified = True
            profile.save(update_fields=['is_identity_verified', 'updated_at'])
            logger.info(
                "Provider %s identity verified after CLEAR background check.",
                bc.provider.email,
            )
    elif bc.status in (
        BackgroundCheck.STATUS_CONSIDER,
        BackgroundCheck.STATUS_SUSPENDED,
        BackgroundCheck.STATUS_CANCELED,
    ):
        if profile.is_identity_verified:
            # Revoke if a new check came back adverse
            profile.is_identity_verified = False
            profile.save(update_fields=['is_identity_verified', 'updated_at'])
            logger.info(
                "Provider %s identity verification revoked (status=%s).",
                bc.provider.email, bc.status,
            )


def _notify_provider(bc: BackgroundCheck):
    """Send a push notification to the provider about their background check result."""
    try:
        from notifications.tasks import send_push_notification_task

        message_map = {
            BackgroundCheck.STATUS_CLEAR: (
                '✅ Background Check Passed',
                'Your background check has cleared! Your profile is now verified.',
            ),
            BackgroundCheck.STATUS_CONSIDER: (
                '⚠️ Background Check Requires Review',
                'Your background check requires further review. We\'ll be in touch.',
            ),
            BackgroundCheck.STATUS_SUSPENDED: (
                '⏸ Background Check Suspended',
                'Your background check has been temporarily suspended.',
            ),
            BackgroundCheck.STATUS_CANCELED: (
                '❌ Background Check Canceled',
                'Your background check was canceled. Please contact support.',
            ),
        }

        if bc.status in message_map:
            title, body = message_map[bc.status]
            device_token = getattr(bc.provider.profile, 'device_token', None)
            if device_token:
                send_push_notification_task.delay(
                    user_id=str(bc.provider_id),
                    title=title,
                    body=body,
                    data={'type': 'background_check', 'status': bc.status},
                )
    except Exception as exc:
        # Notification failure must never break the webhook response
        logger.warning("Failed to send background check notification: %s", exc)
