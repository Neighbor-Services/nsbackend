from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Notification, DeviceToken

@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__email', 'title', 'message')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'notification_type', 'is_read')
        }),
        ('Content', {
            'fields': ('title', 'message', 'data')
        }),
    )


@admin.register(DeviceToken)
class DeviceTokenAdmin(ModelAdmin):
    list_display = ('user', 'token', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'token')

    fieldsets = (
        (None, {
            'fields': ('user', 'token', 'platform', 'is_active')
        }),
        ('Content', {
            'fields': ('token', 'device_id', 'is_active')
        }),
    )