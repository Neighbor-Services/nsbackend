from rest_framework import serializers
import uuid
from .models import Favorite, Review, Appointment, Dispute
from accounts.serializers import ProfileSerializer, SimpleProfileSerializer

class DisputeSerializer(serializers.ModelSerializer):
    raised_by_details = SimpleProfileSerializer(source='raised_by.profile', read_only=True)
    defendant_details = SimpleProfileSerializer(source='defendant.profile', read_only=True)

    class Meta:
        model = Dispute
        fields = [
            'id', 'raised_by', 'defendant', 'appointment', 
            'reason', 'description', 'status', 'resolution_notes', 
            'created_at', 'updated_at',
            'raised_by_details', 'defendant_details'
        ]
        read_only_fields = ['id', 'status', 'resolution_notes', 'created_at', 'updated_at', 'raised_by']
        extra_kwargs = {
            'appointment': {'required': False, 'allow_null': True}
        }
    
    # Explicitly define defendant as UUIDField for input to avoid PK relation issues
    defendant = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    def validate(self, data):
        # If appointment is provided as empty string, set to None
        if 'appointment' in data and data['appointment'] == '':
            data['appointment'] = None
        
        # If defendant is not provided, try to get it from appointment
        if not data.get('defendant') and data.get('appointment'):
            appointment = data['appointment']
            # Set defendant as the other party in the appointment
            request_user = self.context.get('request').user
            if appointment.seeker == request_user:
                data['defendant'] = appointment.provider
            else:
                data['defendant'] = appointment.seeker
        
        # If defendant is provided (as UUID or str), convert to User object
        defendant_input = data.get('defendant')
        if defendant_input and (isinstance(defendant_input, str) or isinstance(defendant_input, uuid.UUID)):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                data['defendant'] = User.objects.get(id=str(defendant_input))
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'defendant': f'User with id {defendant_input} does not exist.'
                })
        
        # If still no defendant, raise validation error
        if not data.get('defendant'):
            raise serializers.ValidationError({
                'defendant': 'Defendant is required. Please provide either a defendant or an appointment.'
            })
        
        return data

    def create(self, validated_data):
        # Allow setting raised_by from context if not present (handled in ViewSet usually)
        return super().create(validated_data)

class FavoriteSerializer(serializers.ModelSerializer):
    favorite_user = SimpleProfileSerializer(source='favorite_user.profile', read_only=True)
    favorite_user_id = serializers.PrimaryKeyRelatedField(
        queryset=Favorite._meta.get_field('favorite_user').remote_field.model.objects.all(),
        source='favorite_user',
        write_only=True
    )
    provider = serializers.PrimaryKeyRelatedField(
        queryset=Favorite._meta.get_field('favorite_user').remote_field.model.objects.all(),
        source='favorite_user',
        write_only=True
    )

    class Meta:
        model = Favorite
        fields = ('id', 'user', 'favorite_user', 'favorite_user_id', 'provider', 'created_at')
        read_only_fields = ('user',)

class ReviewSerializer(serializers.ModelSerializer):
    reviewer_profile = SimpleProfileSerializer(source='reviewer.profile', read_only=True)
    provider_profile = SimpleProfileSerializer(source='provider.profile', read_only=True)
    created_at_formatted = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M:%S", read_only=True)
    profile_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ('reviewer', 'created_at', 'updated_at')
        extra_kwargs = {
            'provider': {'required': False}
        }

    def validate(self, data):
        profile_id = data.pop('profile_id', None)

        if profile_id:
            from accounts.models import Profile, User
            try:
                profile = Profile.objects.select_related('user').get(id=profile_id)
                data['provider'] = profile.user
            except Profile.DoesNotExist:
                try:
                    user = User.objects.get(id=profile_id)
                    data['provider'] = user
                except User.DoesNotExist:
                    raise serializers.ValidationError(
                        {'profile_id': 'Provider not found (Invalid Profile or User ID)'}
                    )

        if 'provider' not in data or data['provider'] is None:
            raise serializers.ValidationError({'provider': 'Provider is required'})

        return data

from django.db import models

class AppointmentSerializer(serializers.ModelSerializer):
    seeker_profile = SimpleProfileSerializer(source='seeker.profile', read_only=True)
    provider_profile = SimpleProfileSerializer(source='provider.profile', read_only=True)
    service_request_details = serializers.SerializerMethodField()

    def get_service_request_details(self, obj):
        """Return a lightweight summary of the linked service request.

        Uses data already loaded by select_related/prefetch_related on the
        ViewSet queryset — no extra DB round-trips.
        """
        req = obj.service_request or (
            obj.proposal.request if obj.proposal else None
        )
        if not req:
            return None

        request_context = self.context.get('request')
        image_url = None
        if req.image:
            if request_context:
                image_url = request_context.build_absolute_uri(req.image.url)
            else:
                image_url = req.image.url

        proposals = list(req.proposals.all())

        return {
            'id': str(req.id),
            'title': req.title,
            'description': req.description,
            'status': req.status,
            'price': str(req.price) if req.price else None,
            'image_url': image_url,
            'scheduled_time': req.scheduled_time.isoformat() if req.scheduled_time else None,
            'created_at': req.created_at.isoformat() if req.created_at else None,
            # Evaluate the prefetch cache ONCE into a local list
            'approved': any(p.is_approved for p in proposals),
            'approved_user': next(
                (str(p.provider.id) for p in proposals if p.is_approved),
                None,
            ),
            'proposals_count': len(proposals),
            'appointment_id': None,
            'is_funded': obj.is_funded,
        }



    class Meta:
        model = Appointment
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'version']

    def validate(self, data):
        # Prevent duplicate appointments
        seeker = data.get('seeker')
        provider = data.get('provider')
        appointment_date = data.get('appointment_date')
        
        if seeker and provider and appointment_date:
            # Check for existing appointment with same seeker, provider and date
            duplicates = Appointment.objects.filter(
                seeker=seeker,
                provider=provider,
                appointment_date=appointment_date
            ).exclude(status='CANCELLED')

            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)

            if duplicates.exists():
                raise serializers.ValidationError("An appointment for this time slots already exists.")

        return super().validate(data)
