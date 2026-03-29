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
        # Debug logging
        print(f"DEBUG REVIEW SERIALIZER: Received data = {data}")
        
    def validate(self, data):
        # Debug logging
        print(f"DEBUG REVIEW SERIALIZER: Received data = {data}")
        
        # If profile_id is provided, resolve it to the user
        profile_id = data.pop('profile_id', None)
        print(f"DEBUG REVIEW SERIALIZER: profile_id = {profile_id}")
        
        if profile_id:
            from accounts.models import Profile, User
            try:
                # Try to find Profile first
                profile = Profile.objects.select_related('user').get(id=profile_id)
                data['provider'] = profile.user
                print(f"DEBUG REVIEW SERIALIZER: Resolved provider from Profile = {profile.user}")
            except Profile.DoesNotExist:
                # Fallback: Try to find User directly
                print(f"DEBUG REVIEW SERIALIZER: Profile not found for id {profile_id}. Checking if it is a User ID...")
                try:
                    user = User.objects.get(id=profile_id)
                    data['provider'] = user
                    print(f"DEBUG REVIEW SERIALIZER: Resolved provider from User ID = {user}")
                except User.DoesNotExist:
                    print(f"DEBUG REVIEW SERIALIZER: User not found for id {profile_id}")
                    raise serializers.ValidationError({'profile_id': 'Provider not found (Invalid Profile or User ID)'})
        
        # Ensure provider is set
        if 'provider' not in data or data['provider'] is None:
            print(f"DEBUG REVIEW SERIALIZER: Provider is missing!")
            raise serializers.ValidationError({'provider': 'Provider is required'})
        
        print(f"DEBUG REVIEW SERIALIZER: Final data = {data}")
        return data
        if 'provider' not in data or data['provider'] is None:
            print(f"DEBUG REVIEW SERIALIZER: Provider is missing!")
            raise serializers.ValidationError({'provider': 'Provider is required'})
        
        print(f"DEBUG REVIEW SERIALIZER: Final data = {data}")
        return data

from django.db import models

class AppointmentSerializer(serializers.ModelSerializer):
    seeker_profile = SimpleProfileSerializer(source='seeker.profile', read_only=True)
    provider_profile = SimpleProfileSerializer(source='provider.profile', read_only=True)

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
