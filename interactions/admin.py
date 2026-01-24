from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Appointment, Review, Favorite, Dispute

@admin.register(Dispute)
class DisputeAdmin(ModelAdmin):
    list_display = ('id', 'raised_by', 'defendant', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('raised_by__email', 'defendant__email', 'reason')

@admin.register(Appointment)
class AppointmentAdmin(ModelAdmin):
    list_display = ('title', 'seeker', 'provider', 'status', 'scheduled_time')
    list_filter = ('status', 'scheduled_time')
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
            'fields': ('scheduled_time', ('start_date', 'end_date'), 'appointment_date')
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
