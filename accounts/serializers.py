from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, PortfolioItem, ServicePackage, User, About, LegalDocument

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_verified:
            raise serializers.ValidationError("Email not verified. Please verify your email before logging in.")
        return data

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'is_verified', 'created_at', 'updated_at')
        extra_kwargs = {
            'password': {'write_only': True},
            'is_verified': {'read_only': True}
        }

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    uidb64 = serializers.CharField(required=True)

class PasswordResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(max_length=4, required=True)
    new_password = serializers.CharField(required=True)

class OTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(max_length=4, required=True)

class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class AboutSerializer(serializers.ModelSerializer):
    class Meta:
        model = About
        fields = '__all__'
        read_only_fields = ('user',)

class ServicePackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePackage
        fields = ['id', 'profile', 'name', 'price', 'description', 'revisions', 'delivery_time', 'features', 'created_at']
        read_only_fields = ['profile', 'created_at']

class PortfolioItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    class Meta:
        model = PortfolioItem
        fields = ('id', 'image', 'description', 'tags', 'created_at', 'image_url')

class SimpleProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    catalog_service_name = serializers.SerializerMethodField()
    catalog_service_names = serializers.SerializerMethodField()
    catalog_service_ids = serializers.SerializerMethodField()
    profile_picture_url = serializers.SerializerMethodField()
    max_catalog_services = serializers.SerializerMethodField()

    def get_catalog_service_name(self, obj):
        first_service = obj.catalog_services.first()
        return first_service.name if first_service else None

    def get_catalog_service_names(self, obj):
        return [cs.name for cs in obj.catalog_services.all()]

    def get_catalog_service_ids(self, obj):
        return [str(cs.id) for cs in obj.catalog_services.all()]

    def get_profile_picture_url(self, obj):
        if obj and obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

    def get_max_catalog_services(self, obj):
        return obj.get_max_catalog_services()

    class Meta:
        model = Profile
        fields = [
            'id', 'user', 'user_type', 'profile_picture_url', 'first_name', 'last_name', 
            'catalog_service_name', 'catalog_service_names', 'catalog_service_ids', 'service', 
            'average_rating', 'total_reviews', 'is_identity_verified', 'preferred_payment_mode', 
            'subscription_tier', 'streak_count', 'xp', 'level', 'neighbor_score',
            'max_catalog_services', 'subscription_interval'
        ]
        read_only_fields = ('average_rating', 'total_reviews', 'is_identity_verified')

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    catalog_service_name = serializers.SerializerMethodField()
    catalog_service_names = serializers.SerializerMethodField()
    catalog_service_ids = serializers.SerializerMethodField()
    profile_picture_url = serializers.SerializerMethodField()
    max_catalog_services = serializers.SerializerMethodField()
    portfolio_items = PortfolioItemSerializer(many=True, read_only=True)
    service_packages = ServicePackageSerializer(many=True, read_only=True)
    reviews_received = serializers.SerializerMethodField()
    
    def get_catalog_service_name(self, obj):
        first_service = obj.catalog_services.first()
        return first_service.name if first_service else None

    def get_catalog_service_names(self, obj):
        return [cs.name for cs in obj.catalog_services.all()]

    def get_catalog_service_ids(self, obj):
        return [str(cs.id) for cs in obj.catalog_services.all()]

    def get_reviews_received(self, obj):
        from interactions.serializers import ReviewSerializer
        reviews = obj.user.reviews_received.select_related(
            'reviewer', 'reviewer__profile', 'provider', 'provider__profile'
        ).all()
        return ReviewSerializer(reviews, many=True, context=self.context).data

    def get_profile_picture_url(self, obj):
        if obj and obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

    def get_max_catalog_services(self, obj):
        return obj.get_max_catalog_services()
    
    def validate_catalog_services(self, value):
        profile = self.instance
        if not profile:
            max_services = 0
        else:
            max_services = profile.get_max_catalog_services()
            
        if len(value) > 0 and max_services == 0:
            raise serializers.ValidationError(
                "An active paid subscription plan is required to offer catalog services."
            )
        elif max_services > 0 and len(value) > max_services:
            raise serializers.ValidationError(
                f"You cannot associate more than {max_services} catalog services on your current subscription plan. "
                f"Please upgrade your subscription for a higher limit."
            )
        return value
    
    class Meta:
        model = Profile
        fields = '__all__'
        read_only_fields = (
            'average_rating', 
            'total_reviews', 
            'is_identity_verified',
            'streak_count',
            'xp',
            'level',
            'neighbor_score'
        )

    def to_internal_value(self, data):
        if 'user_type' in data and not data.get('user_type'):
            if hasattr(data, 'copy'):
                data = data.copy()
            data['user_type'] = 'SEEKER'
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        old_user_type = instance.user_type
        new_user_type = validated_data.get('user_type', old_user_type)

        if old_user_type == 'SEEKER' and new_user_type == 'PROVIDER':
            # 1. Subscription is also required (must be a paid active sub, no FREE auto-creation)
            from payments.models import Subscription
            sub = Subscription.objects.filter(user=instance.user, is_active=True).first()
            if not sub:
                raise serializers.ValidationError(
                    {"user_type": "An active paid subscription plan is required to become a provider."}
                )

        elif old_user_type == 'PROVIDER' and new_user_type == 'SEEKER':
            # 1. Void previous subscription
            from payments.models import Subscription
            Subscription.objects.filter(user=instance.user).delete()
            # 3. Set subscription tier to NONE
            instance.subscription_tier = 'NONE'

        return super().update(instance, validated_data)



class LegalDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalDocument
        fields = ('id', 'doc_type', 'title', 'content', 'version', 'updated_at')

