from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, PortfolioItem, ServicePackage, User, About

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
    otp_code = serializers.CharField(max_length=6, required=True)
    new_password = serializers.CharField(required=True)

class OTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(max_length=6, required=True)

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
    catalog_service_name = serializers.ReadOnlyField(source='catalog_service.name')
    profile_picture_url = serializers.SerializerMethodField()

    def get_profile_picture_url(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

    class Meta:
        model = Profile
        fields = ['id', 'user', 'user_type', 'profile_picture_url', 'first_name', 'last_name', 'catalog_service_name', 'service', 'average_rating', 'total_reviews', 'is_identity_verified']
        read_only_fields = ('average_rating', 'total_reviews', 'is_identity_verified')

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    catalog_service_name = serializers.ReadOnlyField(source='catalog_service.name')
    profile_picture_url = serializers.SerializerMethodField()
    portfolio_items = PortfolioItemSerializer(many=True, read_only=True)
    service_packages = ServicePackageSerializer(many=True, read_only=True)
    reviews_received = serializers.SerializerMethodField()
    
    def get_reviews_received(self, obj):
        from interactions.serializers import ReviewSerializer
        reviews = obj.user.reviews_received.all()
        return ReviewSerializer(reviews, many=True, context=self.context).data

    def get_profile_picture_url(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None
    
    class Meta:
        model = Profile
        fields = '__all__'
        read_only_fields = ('average_rating', 'total_reviews', 'is_identity_verified')
