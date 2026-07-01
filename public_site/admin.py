from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import HeroSection, Feature, Testimonial, FAQ, AboutContent, HowItWorksStep, SiteStat, SiteSetting, ContactMessage, ResolutionReport

@admin.register(HeroSection)
class HeroSectionAdmin(ModelAdmin):
    list_display = ('headline', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('headline', 'subheadline')

@admin.register(Feature)
class FeatureAdmin(ModelAdmin):
    list_display = ('title', 'icon', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('title', 'description')

@admin.register(Testimonial)
class TestimonialAdmin(ModelAdmin):
    list_display = ('name', 'role', 'rating', 'is_active')
    list_filter = ('rating', 'is_active')
    search_fields = ('name', 'content')

@admin.register(FAQ)
class FAQAdmin(ModelAdmin):
    list_display = ('question', 'category', 'order', 'is_active')
    list_filter = ('category', 'is_active')
    list_editable = ('category', 'order', 'is_active')
    search_fields = ('question', 'answer')

@admin.register(AboutContent)
class AboutContentAdmin(ModelAdmin):
    list_display = ('title', 'year_founded', 'cities_covered', 'is_active', 'updated_at')
    list_filter = ('is_active',)

@admin.register(HowItWorksStep)
class HowItWorksStepAdmin(ModelAdmin):
    list_display = ('title', 'order', 'is_active')
    list_editable = ('order', 'is_active')

@admin.register(SiteStat)
class SiteStatAdmin(ModelAdmin):
    list_display = ('label', 'value', 'order', 'is_active')
    list_editable = ('order', 'is_active')

@admin.register(SiteSetting)
class SiteSettingAdmin(ModelAdmin):
    list_display = ('site_name', 'contact_email', 'contact_phone')

@admin.register(ContactMessage)
class ContactMessageAdmin(ModelAdmin):
    list_display = ('inquiry_type', 'first_name', 'last_name', 'email', 'created_at', 'is_resolved')
    list_filter = ('inquiry_type', 'is_resolved', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'message')

@admin.register(ResolutionReport)
class ResolutionReportAdmin(ModelAdmin):
    list_display = ('issue_type', 'role', 'created_at', 'is_reviewed')
    list_filter = ('issue_type', 'role', 'is_reviewed', 'created_at')
    search_fields = ('booking_ref', 'description', 'expected_outcome')
