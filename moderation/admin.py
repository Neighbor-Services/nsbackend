import json

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import Report, ProviderVerification, BackgroundCheck, ModerationSetting


@admin.register(ModerationSetting)
class ModerationSettingAdmin(ModelAdmin):
    list_display = ('id', 'background_check_payment_mode', 'background_check_fee')

@admin.register(Report)
class ReportAdmin(ModelAdmin):
    list_display = ('reporter', 'reported_user', 'resource_type', 'status', 'created_at')
    list_filter = ('status', 'resource_type', 'created_at')
    search_fields = ('reporter__email', 'reported_user__email', 'reason')


@admin.register(ProviderVerification)
class ProviderVerificationAdmin(ModelAdmin):
    list_display = ('provider', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('provider__email', 'reviewer_notes')
    actions = ['approve_verification', 'reject_verification']

    @admin.action(description="Approve selected verifications")
    def approve_verification(self, request, queryset):
        for verification in queryset:
            verification.status = 'APPROVED'
            verification.save()
            # Update the user's profile
            profile = verification.provider.profile
            profile.is_identity_verified = True
            profile.save()
        self.message_user(request, f"{queryset.count()} providers verified.")

    @admin.action(description="Reject selected verifications")
    def reject_verification(self, request, queryset):
        queryset.update(status='REJECTED')
        self.message_user(request, f"{queryset.count()} verifications rejected.")


@admin.register(BackgroundCheck)
class BackgroundCheckAdmin(ModelAdmin):
    list_display = (
        'provider_email',
        'status_badge',
        'adjudication',
        'package',
        'sync_attempt_count',
        'last_synced_at',
        'created_at',
    )
    list_filter = ('status', 'adjudication', 'package', 'created_at')
    search_fields = (
        'provider__email',
        'checkr_candidate_id',
        'checkr_report_id',
        'checkr_invitation_id',
    )
    readonly_fields = (
        'id',
        'provider',
        'checkr_candidate_id',
        'checkr_report_id',
        'checkr_invitation_id',
        'invitation_url',
        'status',
        'adjudication',
        'result_pretty',
        'last_synced_at',
        'sync_attempt_count',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        ('Provider', {
            'fields': ('id', 'provider'),
        }),
        ('Checkr Identifiers', {
            'fields': (
                'checkr_candidate_id',
                'checkr_report_id',
                'checkr_invitation_id',
                'invitation_url',
            ),
        }),
        ('Check Status', {
            'fields': ('package', 'status', 'adjudication'),
        }),
        ('Sync Tracking', {
            'fields': ('sync_attempt_count', 'last_synced_at'),
        }),
        ('Raw Report Data', {
            'fields': ('result_pretty',),
            'classes': ('collapse',),
        }),
        ('Internal Notes', {
            'fields': ('notes',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    actions = ['resync_from_checkr', 'mark_clear_manually', 'mark_consider_manually']

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description='Provider', ordering='provider__email')
    def provider_email(self, obj):
        return obj.provider.email

    @admin.display(description='Status')
    def status_badge(self, obj):
        color_map = {
            'PENDING': '#f59e0b',
            'CLEAR': '#10b981',
            'CONSIDER': '#ef4444',
            'SUSPENDED': '#6366f1',
            'DISPUTE': '#f97316',
            'CANCELED': '#9ca3af',
        }
        color = color_map.get(obj.status, '#9ca3af')
        return format_html(
            '<span style="'
            'background:{color};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;">'
            '{status}</span>',
            color=color,
            status=obj.status,
        )

    @admin.display(description='Checkr Report (JSON)')
    def result_pretty(self, obj):
        if obj.result:
            formatted = json.dumps(obj.result, indent=2)
            return format_html(
                '<pre style="max-height:400px;overflow:auto;'
                'background:#1e1e2e;color:#cdd6f4;padding:12px;'
                'border-radius:6px;font-size:12px;">{}</pre>',
                formatted,
            )
        return '—'

    # ------------------------------------------------------------------
    # Admin actions
    # ------------------------------------------------------------------

    @admin.action(description='🔄 Re-sync from Checkr API')
    def resync_from_checkr(self, request, queryset):
        from .tasks import sync_checkr_report_task
        queued = 0
        skipped = 0
        for bc in queryset:
            if bc.checkr_report_id:
                sync_checkr_report_task.delay(str(bc.id))
                queued += 1
            else:
                skipped += 1
        msg = f"{queued} check(s) queued for re-sync."
        if skipped:
            msg += f" {skipped} skipped (no report ID yet)."
        self.message_user(request, msg)

    @admin.action(description='✅ Manually mark as CLEAR (override)')
    def mark_clear_manually(self, request, queryset):
        from .views import _sync_provider_identity
        for bc in queryset:
            bc.status = BackgroundCheck.STATUS_CLEAR
            bc.notes = (bc.notes or '') + '\n[Admin manually set to CLEAR]'
            bc.save()
            _sync_provider_identity(bc)
        self.message_user(request, f"{queryset.count()} check(s) marked CLEAR.")

    @admin.action(description='⚠️ Manually mark as CONSIDER (override)')
    def mark_consider_manually(self, request, queryset):
        from .views import _sync_provider_identity
        for bc in queryset:
            bc.status = BackgroundCheck.STATUS_CONSIDER
            bc.notes = (bc.notes or '') + '\n[Admin manually set to CONSIDER]'
            bc.save()
            _sync_provider_identity(bc)
        self.message_user(request, f"{queryset.count()} check(s) marked CONSIDER.")
