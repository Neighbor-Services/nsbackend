from django.urls import path
from .views import ConsultationTokenView, ConsultationRTMTokenView

urlpatterns = [
    path('rtc-token/', ConsultationTokenView.as_view(), name='agora-rtc-token'),
    path('rtm-token/', ConsultationRTMTokenView.as_view(), name='agora-rtm-token'),
]
