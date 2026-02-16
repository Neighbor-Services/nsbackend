from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Notification

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
