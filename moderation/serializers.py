from rest_framework import serializers
from .models import Report, ProviderVerification

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
