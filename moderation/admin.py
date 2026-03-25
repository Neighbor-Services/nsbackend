from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Report, ProviderVerification

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
