from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Category, CatalogService, ServiceRequest, Proposal

@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(CatalogService)
class CatalogServiceAdmin(ModelAdmin):
    list_display = ('name', 'category', 'base_price', 'created_at')
    list_filter = ('category',)
    search_fields = ('name', 'category__name')

class ProposalInline(TabularInline):
    model = Proposal
    extra = 0

@admin.register(ServiceRequest)
class ServiceRequestAdmin(ModelAdmin):
    list_display = ('title', 'user', 'price', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'user__email', 'description')
    inlines = [ProposalInline]
    
    fieldsets = (
        ('Context', {
            'fields': ('user', 'catalog_service', 'status')
        }),
        ('Content', {
            'fields': ('title', 'description', 'image', 'with_image')
        }),
        ('Logistics', {
            'fields': ('price', 'scheduled_time', ('latitude', 'longitude'))
        }),
        ('Legacy', {
            'fields': ('service_type',),
            'classes': ('collapse',),
        }),
    )

@admin.register(Proposal)
class ProposalAdmin(ModelAdmin):
    list_display = ('provider_email', 'request_title', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'created_at')
    search_fields = ('provider__email', 'request__title')

    def provider_email(self, obj):
        return obj.provider.email
    
    def request_title(self, obj):
        return obj.request.title
