from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .utils import AgoraTokenService
import uuid
from notifications.utils import send_notification
from django.contrib.auth import get_user_model

User = get_user_model()

class ConsultationTokenView(APIView):
    """
    API endpoint to generate Agora RTC tokens for video/audio consultations.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        channel_name = request.query_params.get('channel_name')
        uid = request.query_params.get('uid', 0)
        
        if not channel_name:
            return Response(
                {"error": "channel_name is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            uid = int(uid)
        except ValueError:
            return Response(
                {"error": "uid must be an integer"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        token = AgoraTokenService.generate_rtc_token(channel_name, uid=uid)
        
        if not token:
            return Response(
                {"error": "Could not generate token. Check server configuration."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Optional: Notify a specific user about an incoming call
        to_user_id = request.query_params.get('to_user_id')
        if to_user_id:
            try:
                target_user = User.objects.get(id=to_user_id)
                send_notification(
                    user=target_user,
                    sender=request.user,
                    title="Incoming Call",
                    message=f"{request.user.email} is calling you.",
                    notification_type="SYSTEM", # Maybe add 'CALL' type later
                    data={
                        "channel_name": channel_name,
                        "type": "video_call_invite",
                        "token": token # Pass token for recipient as well
                    }
                )
            except User.DoesNotExist:
                pass

        return Response({
            "token": token,
            "channel_name": channel_name,
            "uid": uid,
            "app_id": AgoraTokenService.get_app_id()
        })

class ConsultationRTMTokenView(APIView):
    """
    API endpoint to generate Agora RTM tokens for signaling.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = str(request.user.id)
        token = AgoraTokenService.generate_rtm_token(user_id)
        
        if not token:
            return Response(
                {"error": "Could not generate token."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            "token": token,
            "user_id": user_id
        })
