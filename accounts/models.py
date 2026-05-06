from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from encrypted_model_fields.fields import EncryptedCharField, EncryptedTextField, EncryptedDateField

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

from django.utils import timezone
import datetime

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

class Profile(models.Model):
    USER_TYPES = (
        ('SEEKER', 'Seeker'),
        ('PROVIDER', 'Provider'),
    )
    GENDERS = (
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
    )
    TIERS = (
        ("NONE", "None"),
        ('FREE', 'Free'),
        ('SILVER', 'Silver'),
        ('GOLD', 'Gold'),
        ('PLATINUM', 'Platinum'),
    )

    PAYMENT_MODES = (
        ('IN_APP', 'In-App Payment'),
        ('ON_SITE', 'On-Site Payment'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    subscription_tier = models.CharField(max_length=10, choices=TIERS, default='NONE')
    preferred_payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, default='ON_SITE')
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = EncryptedDateField(blank=True, null=True)
    catalog_service = models.ForeignKey('services.CatalogService', on_delete=models.SET_NULL, null=True, blank=True, related_name='profiles')
    service = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GENDERS, blank=True, null=True)
    country_code = models.CharField(max_length=10, blank=True, null=True)
    phone = EncryptedCharField(max_length=20, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = EncryptedTextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPES, default='SEEKER')
    longitude = models.DecimalField(max_digits=22, decimal_places=16, blank=True, null=True)
    latitude = models.DecimalField(max_digits=22, decimal_places=16, blank=True, null=True)
    device_token = models.CharField(max_length=255, blank=True, null=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    is_identity_verified = models.BooleanField(default=False)
    
    bio = models.TextField(blank=True, null=True)
    bio_embedding = models.JSONField(blank=True, null=True)

    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    # Gamification Fields
    streak_count = models.IntegerField(default=0)
    last_check_in = models.DateField(blank=True, null=True)
    xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    neighbor_score = models.IntegerField(default=500) # Base score starts at 500

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_identity_verified']),
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['average_rating']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.email})"

    def get_commission_rate(self):
        """Returns the platform commission rate based on subscription tier"""
        rates = {
            'FREE': 0.20,
            'SILVER': 0.15,
            'GOLD': 0.10,
            'PLATINUM': 0.05,
        }
        return rates.get(self.subscription_tier, 0.20)

    def record_activity(self):
        """Updates streaks based on daily activity"""
        today = timezone.now().date()
        if self.last_check_in:
            if self.last_check_in == today:
                return # Already checked in today
            
            yesterday = today - datetime.timedelta(days=1)
            if self.last_check_in == yesterday:
                self.streak_count += 1
            else:
                self.streak_count = 1 # Streak broken
        else:
            self.streak_count = 1
        
        self.last_check_in = today
        self.save(update_fields=['streak_count', 'last_check_in'])

    def award_xp(self, amount):
        """Awards XP and checks for level up"""
        self.xp += amount
        # Simple level calculation: 1000 XP per level
        new_level = (self.xp // 1000) + 1
        if new_level > self.level:
            self.level = new_level
            # Maybe send a notification here in the future
        self.save(update_fields=['xp', 'level'])

    def priority_score(self):
        """Returns a priority score for AI matching boosts"""
        scores = {
            'FREE': 1.0,
            'SILVER': 1.1,
            'GOLD': 1.2,
            'PLATINUM': 1.5,
        }
        return scores.get(self.subscription_tier, 1.0)

class About(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='about_info')
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    country_code = models.CharField(max_length=5, blank=True, null=True)
    specification = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image_urls = models.JSONField(default=list, blank=True)
    
    # Professional Fields
    experience_years = models.PositiveIntegerField(default=0)
    skills = models.JSONField(default=list, blank=True)
    education = models.TextField(blank=True, null=True)
    languages = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"About {self.name}"

class PortfolioItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='portfolio_items')
    image = models.ImageField(upload_to='portfolio/')
    description = models.CharField(max_length=255, blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Portfolio for {self.profile.user.email}"

class ServicePackage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='service_packages')
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    revisions = models.IntegerField(default=0)
    delivery_time = models.IntegerField(default=1) # Days
    features = models.JSONField(default=list, blank=True)
    
    # AI Field
    description_embedding = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.price}"

class PerformanceBadge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='performance_badges')
    name = models.CharField(max_length=100)
    icon_type = models.CharField(max_length=50) # bolt, star, shield, etc.
    awarded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} for {self.profile.user.email}"


class LegalDocument(models.Model):
    DOC_TYPES = (
        ('TERMS', 'Terms & Conditions'),
        ('PRIVACY', 'Privacy Policy'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type = models.CharField(max_length=10, choices=DOC_TYPES)
    title = models.CharField(max_length=255)
    content = models.TextField()
    version = models.CharField(max_length=20, default='1.0')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Legal Document'
        verbose_name_plural = 'Legal Documents'
        indexes = [
            models.Index(fields=['doc_type', 'is_active', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_doc_type_display()} v{self.version}"
