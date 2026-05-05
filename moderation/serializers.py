from rest_framework import serializers
from .models import Report, ProviderVerification, BackgroundCheck


class ReportSerializer(serializers.ModelSerializer):
    reporter_email = serializers.ReadOnlyField(source='reporter.email')

    class Meta:
        model = Report
        fields = '__all__'
        read_only_fields = ('reporter', 'status', 'admin_note')


class ProviderVerificationSerializer(serializers.ModelSerializer):
    document_front_url = serializers.SerializerMethodField()
    document_back_url = serializers.SerializerMethodField()

    def get_document_front_url(self, obj):
        if obj.document_front:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document_front.url)
            return obj.document_front.url
        return None

    def get_document_back_url(self, obj):
        if obj.document_back:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document_back.url)
            return obj.document_back.url
        return None

    class Meta:
        model = ProviderVerification
        fields = '__all__'
        read_only_fields = ('provider', 'status', 'reviewer_notes', 'created_at', 'updated_at')


class BackgroundCheckSerializer(serializers.ModelSerializer):
    """
    Serializer for BackgroundCheck.

    - Checkr-internal IDs (candidate_id, report_id, invitation_id) are
      read-only and hidden from non-staff users via the view layer.
    - `invitation_url` is returned on creation so the mobile app can
      redirect the provider to Checkr's hosted form.
    - `result` (raw Checkr JSON) is omitted from the default response;
      the admin panel reads it directly.
    """

    provider_email = serializers.ReadOnlyField(source='provider.email')
    is_clear = serializers.ReadOnlyField()
    is_terminal = serializers.ReadOnlyField()

    class Meta:
        model = BackgroundCheck
        fields = [
            'id',
            'provider',
            'provider_email',
            'checkr_candidate_id',
            'checkr_report_id',
            'checkr_invitation_id',
            'invitation_url',
            'package',
            'status',
            'adjudication',
            'is_clear',
            'is_terminal',
            'last_synced_at',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = (
            'provider',
            'checkr_candidate_id',
            'checkr_report_id',
            'checkr_invitation_id',
            'invitation_url',
            'status',
            'adjudication',
            'is_clear',
            'is_terminal',
            'last_synced_at',
            'created_at',
            'updated_at',
        )
