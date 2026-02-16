from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ('user', 'action', 'resource_type', 'created_at')
    list_filter = ('action', 'resource_type', 'created_at')
    search_fields = ('user__email', 'action', 'details')
