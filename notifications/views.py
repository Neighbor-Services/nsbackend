from rest_framework import viewsets, permissions, status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Notification, DeviceToken
from .serializers import NotificationSerializer, DeviceTokenSerializer
from ns_backend.cache_utils import invalidate_cache_pattern
from django.core.cache import cache

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.select_related('user').all()
    serializer_class = NotificationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Set current user as sender if not provided, 
        # and ensure the user (recipient) is set from data
        notification = serializer.save(sender=self.request.user)
        
        # Trigger background delivery (FCM, etc.)
        from .utils import send_notification
        from .tasks import send_notification_delivery_task
        from django.db import transaction
        
        def trigger_task():
            send_notification_delivery_task.delay(str(notification.id))

        transaction.on_commit(trigger_task)

    def list(self, request, *args, **kwargs):
        # Include page and query params in cache key to avoid returning wrong page
        page = request.query_params.get('page', '1')
        cache_key = f"notifications_user_{request.user.id}_page_{page}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(cache_key, response.data, 60 * 5) # 5 mins
        return response

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        cache.delete(f"notifications_user_{request.user.id}")
        return Response({'status': 'notification marked as read'})

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        self.get_queryset().update(is_read=True)
        cache.delete(f"notifications_user_{request.user.id}")
        return Response({'status': 'all notifications marked as read'})

class DeviceTokenViewSet(viewsets.ModelViewSet):
    queryset = DeviceToken.objects.all()
    serializer_class = DeviceTokenSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """
        Upsert a device token: update if token already exists, create otherwise.
        Returns 200 on update, 201 on create — so the Flutter client always
        gets a success response regardless of whether this is a new registration.
        """
        token = request.data.get('token')
        device_id = request.data.get('device_id')
        platform = request.data.get('platform')

        if not token or not platform:
            return Response(
                {'detail': 'Both token and platform are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'device_id': device_id,
                'platform': platform,
                'is_active': True,
            },
        )

        serializer = self.get_serializer(obj)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=http_status)
