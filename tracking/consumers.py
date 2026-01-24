import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from interactions.models import Appointment
import logging

logger = logging.getLogger(__name__)

class TrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.appointment_id = self.scope['url_route']['kwargs']['appointment_id']
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        # Verify user is part of the appointment
        self.appointment = await self.get_appointment(self.appointment_id)
        if not self.appointment or (self.appointment.seeker != self.user and self.appointment.provider != self.user):
            await self.close()
            return

        self.room_group_name = f'tracking_{self.appointment_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        
        # Only provider can send updates
        if self.user == self.appointment.provider:
            lat = data.get('latitude')
            lng = data.get('longitude')
            heading = data.get('heading')
            
            if lat and lng:
                # Update location in Redis or temporary storage if needed for persistence
                # For now, just broadcast to the seeker
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'location_update',
                        'location_data': {
                            'latitude': lat,
                            'longitude': lng,
                            'heading': heading,
                            'provider_id': str(self.user.id)
                        }
                    }
                )

    async def location_update(self, event):
        # Send location to frontend
        await self.send(text_data=json.dumps(event['location_data']))

    @database_sync_to_async
    def get_appointment(self, appointment_id):
        try:
            return Appointment.objects.select_related('seeker', 'provider').get(id=appointment_id)
        except Appointment.DoesNotExist:
            return None
