from django.shortcuts import render, redirect
from django.contrib import messages
import json
from django.http import JsonResponse
from .models import (
    HeroSection, Feature, Testimonial, FAQ, 
    AboutContent, HowItWorksStep, SiteStat,
    ContactMessage, ResolutionReport
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

def support(request):
    # Fetch FAQs grouped by category
    faqs = FAQ.objects.filter(is_active=True).order_by('order')
    categories = FAQ.FAQ_CATEGORIES
    faq_data = []
    for cat_val, cat_label in categories:
        cat_faqs = [faq for faq in faqs if faq.category == cat_val]
        if cat_faqs:
            faq_data.append({
                'category_val': cat_val,
                'category_label': cat_label,
                'faqs': cat_faqs
            })
    
    return render(request, 'public_site/support.html', {'faq_data': faq_data})

def contact(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        inquiry_type = request.POST.get('inquiry_type', '')
        message = request.POST.get('message', '')
        
        if first_name and email and message:
            ContactMessage.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                inquiry_type=inquiry_type,
                message=message
            )
            messages.success(request, 'Your message has been sent successfully. We will get back to you shortly.')
            return redirect('public_site:contact')
        else:
            messages.error(request, 'Please fill in all required fields.')

    return render(request, 'public_site/contact.html')

def privacy(request):
    docs = LegalDocument.objects.filter(doc_type='PRIVACY', is_active=True).order_by('-updated_at')
    return render(request, 'public_site/privacy.html', {'docs': docs})

def terms(request):
    docs = LegalDocument.objects.filter(doc_type='TERMS', is_active=True).order_by('-updated_at')
    return render(request, 'public_site/terms.html', {'docs': docs})

def resolution(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ResolutionReport.objects.create(
                role=data.get('role', ''),
                issue_type=data.get('issue_type', ''),
                booking_ref=data.get('booking_ref', ''),
                other_neighbor=data.get('other_neighbor', ''),
                date_of_service=data.get('date_of_service') or None,
                description=data.get('description', ''),
                expected_outcome=data.get('expected_outcome', '')
            )
            return JsonResponse({'status': 'success', 'message': 'Resolution report submitted successfully.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return render(request, 'public_site/resolution.html')
