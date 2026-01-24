from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from .models import User, Profile, PortfolioItem, About

class ProfileInline(StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'

class UserAdmin(BaseUserAdmin, ModelAdmin):
    inlines = (ProfileInline,)
    list_display = ('email', 'is_staff', 'is_active', 'is_verified', 'created_at')
    list_filter = ('is_staff', 'is_active', 'is_verified')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ()}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at')}),
    )
    readonly_fields = ('created_at',)

class PortfolioInline(TabularInline):
    model = PortfolioItem
    extra = 0

@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ('user_email', 'first_name', 'last_name', 'user_type', 'city', 'average_rating', 'total_reviews')
    list_filter = ('user_type', 'city', 'gender')
    search_fields = ('user__email', 'first_name', 'last_name', 'city')
    inlines = [PortfolioInline]
    
    fieldsets = (
        ('User Info', {
            'fields': ('user', 'user_type', 'profile_picture')
        }),
        ('Personal Details', {
            'fields': (('first_name', 'last_name'), 'gender', 'date_of_birth', 'bio')
        }),
        ('Service Info', {
            'fields': ('catalog_service', 'service', 'average_rating', 'total_reviews')
        }),
        ('Contact & Location', {
            'fields': (('country_code', 'phone'), 'address', 'city', 'state', 'country', 'zip_code', ('latitude', 'longitude'))
        }),
        ('System', {
            'fields': ('device_token', 'bio_embedding')
        }),
    )
    readonly_fields = ('average_rating', 'total_reviews', 'bio_embedding')

    def user_email(self, obj):
        return obj.user.email

@admin.register(About)
class AboutAdmin(ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    search_fields = ('name', 'user__email')

@admin.register(PortfolioItem)
class PortfolioItemAdmin(ModelAdmin):
    list_display = ('profile', 'description', 'created_at')
    search_fields = ('profile__user__email', 'description')

# admin.site.unregister(User) # BaseUserAdmin was not registered yet in this file
admin.site.register(User, UserAdmin)
