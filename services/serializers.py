from rest_framework import serializers
from .models import ServiceRequest, Proposal, Category, CatalogService
from accounts.serializers import ProfileSerializer

class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

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
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

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

    def _get_proposals(self, obj):
        """Evaluate the prefetch cache exactly once per serialized object."""
        if not hasattr(obj, '_proposals_cache'):
            obj._proposals_cache = list(obj.proposals.all())
        return obj._proposals_cache

    def _get_appointments(self, obj):
        if not hasattr(obj, '_appointments_cache'):
            obj._appointments_cache = list(obj.appointments.all())
        return obj._appointments_cache

    def get_proposals_count(self, obj):
        return len(self._get_proposals(obj))

    def get_approved_user(self, obj):
        approved_proposal = next(
            (p for p in self._get_proposals(obj) if p.is_approved), None
        )
        if approved_proposal:
            try:
                return ProfileSerializer(
                    approved_proposal.provider.profile,
                    context=self.context,
                ).data
            except Exception:
                return None
        return None

    def get_approved(self, obj):
        return any(p.is_approved for p in self._get_proposals(obj))

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_distance(self, obj):
        if hasattr(obj, 'distance') and obj.distance is not None:
            return obj.distance
        return None

    def get_appointment_id(self, obj):
        appts = self._get_appointments(obj)
        return str(appts[0].id) if appts else None

    def get_is_funded(self, obj):
        appts = self._get_appointments(obj)
        return appts[0].is_funded if appts else False

    class Meta:
        model = ServiceRequest
        fields = '__all__'
        read_only_fields = ('user',)
        extra_kwargs = {
            'target_provider': {'required': False}
        }
