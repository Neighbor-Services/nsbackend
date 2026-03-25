from rest_framework import viewsets, permissions
from .models import Report, ProviderVerification
from .serializers import ReportSerializer, ProviderVerificationSerializer

class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)
class ProviderVerificationViewSet(viewsets.ModelViewSet):
    queryset = ProviderVerification.objects.all()
    serializer_class = ProviderVerificationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(provider=self.request.user)

    def perform_create(self, serializer):
        # Only allow one pending/active verification at a time? 
        # For now, just allow creation.
        serializer.save(provider=self.request.user)
