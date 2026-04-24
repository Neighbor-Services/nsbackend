from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import HeroSection, Feature, Testimonial, FAQ, AboutContent, HowItWorksStep, SiteStat, SiteSetting

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
    list_display = ('question', 'order', 'is_active')
    list_editable = ('order', 'is_active')
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
