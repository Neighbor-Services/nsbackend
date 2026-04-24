from django.shortcuts import render
from .models import (
    HeroSection, Feature, Testimonial, FAQ, 
    AboutContent, HowItWorksStep, SiteStat
)
from accounts.models import LegalDocument
from services.models import CatalogService, Category

def index(request):
    hero = HeroSection.objects.filter(is_active=True).first()
    features = Feature.objects.filter(is_active=True)
    testimonials = Testimonial.objects.filter(is_active=True)
    faqs = FAQ.objects.filter(is_active=True)
    steps = HowItWorksStep.objects.filter(is_active=True)
    stats = SiteStat.objects.filter(is_active=True)
    
    # Showcase some services on the home page
    catalog_services = CatalogService.objects.all().select_related('category')[:6]
    
    context = {
        'hero': hero,
        'features': features,
        'testimonials': testimonials,
        'faqs': faqs,
        'steps': steps,
        'stats': stats,
        'catalog_services': catalog_services,
    }
    return render(request, 'public_site/index.html', context)

def about(request):
    about_content = AboutContent.objects.filter(is_active=True).first()
    return render(request, 'public_site/about.html', {'about': about_content})

def services(request):
    categories = Category.objects.all().prefetch_related('services')
    all_services = CatalogService.objects.all().select_related('category')
    
    context = {
        'categories': categories,
        'all_services': all_services,
    }
    return render(request, 'public_site/services.html', context)

def contact(request):
    return render(request, 'public_site/contact.html')

def privacy(request):
    doc = LegalDocument.objects.filter(doc_type='PRIVACY', is_active=True).order_by('-updated_at').first()
    return render(request, 'public_site/privacy.html', {'doc': doc})

def terms(request):
    doc = LegalDocument.objects.filter(doc_type='TERMS', is_active=True).order_by('-updated_at').first()
    return render(request, 'public_site/terms.html', {'doc': doc})
