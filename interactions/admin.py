from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Appointment, Review, Favorite, Dispute
from audit.utils import log_audit_action

@admin.register(Dispute)
class DisputeAdmin(ModelAdmin):
    list_display = ('id', 'raised_by', 'defendant', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('raised_by__email', 'defendant__email', 'reason')
    
    actions = ['resolve_disputes', 'reject_disputes']
    
    @admin.action(description='Mark selected disputes as Resolved')
    def resolve_disputes(self, request, queryset):
        for dispute in queryset:
            log_audit_action(
                user=request.user,
                action='ADMIN_RESOLVE_DISPUTE',
                resource_type='Dispute',
                resource_id=dispute.id,
                details={'status': 'RESOLVED'},
                request=request
            )
        updated = queryset.update(status='RESOLVED')
        self.message_user(request, f'{updated} dispute(s) marked as resolved.')

    @admin.action(description='Mark selected disputes as Rejected')
    def reject_disputes(self, request, queryset):
        for dispute in queryset:
            log_audit_action(
                user=request.user,
                action='ADMIN_REJECT_DISPUTE',
                resource_type='Dispute',
                resource_id=dispute.id,
                details={'status': 'REJECTED'},
                request=request
            )
        updated = queryset.update(status='REJECTED')
        self.message_user(request, f'{updated} dispute(s) marked as rejected.')

@admin.register(Appointment)
class AppointmentAdmin(ModelAdmin):
    list_display = ('title', 'seeker', 'provider', 'status')
    list_filter = ('status',)
    search_fields = ('title', 'seeker__email', 'provider__email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Context', {
            'fields': ('title', 'status')
        }),
        ('Participants', {
            'fields': ('seeker', 'provider')
        }),
        ('Schedule', {
            'fields': ('appointment_date',)
        }),
        ('Content', {
            'fields': ('description',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ('provider', 'reviewer', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('provider__email', 'reviewer__email', 'comment')
    readonly_fields = ('created_at',)

@admin.register(Favorite)
class FavoriteAdmin(ModelAdmin):
    list_display = ('user', 'favorite_user', 'created_at')
    search_fields = ('user__email', 'favorite_user__email')
