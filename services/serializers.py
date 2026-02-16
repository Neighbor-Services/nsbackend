from rest_framework import serializers
from .models import ServiceRequest, Proposal, Category, CatalogService
from accounts.serializers import ProfileSerializer

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class CatalogServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = CatalogService
        fields = '__all__'
        extra_kwargs = {
            'category': {'required': False}
        }

class ProposalSerializer(serializers.ModelSerializer):
    provider_profile = ProfileSerializer(source='provider.profile', read_only=True)
    provider_email = serializers.ReadOnlyField(source='provider.email')
    seeker_profile = ProfileSerializer(source='request.user.profile', read_only=True)
    service_request = serializers.PrimaryKeyRelatedField(
        queryset=ServiceRequest.objects.all(),
        source='request',
        write_only=True,
        required=True
    )

    class Meta:
        model = Proposal
        fields = '__all__'
        read_only_fields = ('provider', 'is_approved', 'request')

class ServiceRequestSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source='user.email')
    user_profile = ProfileSerializer(source='user.profile', read_only=True)
    catalog_service_name = serializers.ReadOnlyField(source='catalog_service.name')
    proposals = ProposalSerializer(many=True, read_only=True)
    distance = serializers.SerializerMethodField()
    approved_user = serializers.SerializerMethodField()
    proposals_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    approved = serializers.SerializerMethodField()
    appointment_id = serializers.SerializerMethodField()
    is_funded = serializers.SerializerMethodField()
    service = serializers.PrimaryKeyRelatedField(
        queryset=CatalogService.objects.all(),
        source='catalog_service',
        write_only=True,
        required=False,
        allow_null=True
    )

    def get_proposals_count(self, obj):
        return obj.proposals.count()

    def get_approved_user(self, obj):
        approved_proposal = obj.proposals.filter(is_approved=True).first()
        if approved_proposal:
            return ProfileSerializer(approved_proposal.provider.profile, context=self.context).data
        return None

    def get_approved(self, obj):
        return obj.proposals.filter(is_approved=True).exists()

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_distance(self, obj):
        # 1. Prefer DB annotation if available (Consistency)
        if hasattr(obj, 'distance') and obj.distance is not None:
            # print(f"DEBUG: Using DB Distance: {obj.distance}")
            return obj.distance

        request = self.context.get('request')
        if not request:
            return None
            
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        
        if lat and lng:
            from ns_backend.utils import haversine_distance
            try:
                dist = haversine_distance(lat, lng, obj.latitude, obj.longitude)
                print(f"DEBUG: Calc Distance: User({lat}, {lng}) -> Target({obj.latitude}, {obj.longitude}) = {dist} km")
                return dist
            except Exception as e:
                print(f"DEBUG: Distance Calc Error: {e}")
                return None
        return None

    def get_appointment_id(self, obj):
        appointment = obj.appointments.first() # Using related_name='appointments'
        return str(appointment.id) if appointment else None

    def get_is_funded(self, obj):
        appointment = obj.appointments.first()
        return appointment.is_funded if appointment else False

    class Meta:
        model = ServiceRequest
        fields = '__all__'
        read_only_fields = ('user',)
        extra_kwargs = {
            'target_provider': {'required': False}
        }
