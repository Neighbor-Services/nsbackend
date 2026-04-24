from django.db import models
import uuid

class HeroSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    headline = models.CharField(max_length=255)
    subheadline = models.TextField()
    cta_text = models.CharField(max_length=50, default="Get Started")
    cta_link = models.CharField(max_length=255, default="#")
    image = models.ImageField(upload_to='public_site/hero/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.headline

class Feature(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, help_text="Material icon name or FontAwesome class")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title

class Testimonial(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, blank=True, null=True)
    content = models.TextField()
    image = models.ImageField(upload_to='public_site/testimonials/', blank=True, null=True)
    rating = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Testimonial from {self.name}"

class FAQ(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.CharField(max_length=255)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question

class AboutContent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Our Mission")
    story_headline = models.CharField(max_length=255, default="Our Story")
    story_text_1 = models.TextField()
    story_text_2 = models.TextField(blank=True, null=True)
    mission_text = models.TextField()
    vision_text = models.TextField()
    year_founded = models.CharField(max_length=10, default="2025")
    cities_covered = models.CharField(max_length=50, default="50+")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "About Page Content"

    def __str__(self):
        return f"About Content (Updated: {self.updated_at})"

class HowItWorksStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100)
    description = models.TextField()
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Step {self.order}: {self.title}"

class SiteStat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=100)
    value = models.CharField(max_length=50)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.label}: {self.value}"

class SiteSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site_name = models.CharField(max_length=100, default="Neighbor Service")
    contact_email = models.EmailField(default="support@neighborservice.com")
    contact_phone = models.CharField(max_length=50, default="+1 (555) 000-0000")
    contact_address = models.TextField(default="123 Community City, CC 12345")
    facebook_url = models.URLField(blank=True, null=True)
    twitter_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Site Global Setting"

    def __str__(self):
        return f"Site Settings: {self.site_name}"
