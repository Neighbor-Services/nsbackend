from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .utils import AgoraTokenService
import uuid

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

        return Response({
            "token": token,
            "channel_name": channel_name,
            "uid": uid,
            "app_id": AgoraTokenService.get_app_id() # Helper needed
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
