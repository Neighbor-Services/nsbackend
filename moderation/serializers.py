from rest_framework import serializers
from .models import Report, ProviderVerification

class ReportSerializer(serializers.ModelSerializer):
    reporter_email = serializers.ReadOnlyField(source='reporter.email')

    class Meta:
        model = Report
        fields = '__all__'
        read_only_fields = ('reporter', 'status', 'admin_note')
class ProviderVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderVerification
        fields = '__all__'
        read_only_fields = ('provider', 'status', 'reviewer_notes', 'created_at', 'updated_at')
