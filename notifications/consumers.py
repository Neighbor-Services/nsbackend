import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
        else:
            self.group_name = f"user_{self.user.id}"
            print(f"WS Consumer: User {self.user.id} joining group {self.group_name}")
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()
            print(f"WS Consumer: Connection accepted for user {self.user.id}")

    async def disconnect(self, close_code):
        print(f"WS Consumer: Disconnected for user {getattr(self, 'user', 'Unknown')} with code {close_code}")
        if hasattr(self, 'group_name') and not self.user.is_anonymous:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        # We don't expect to receive messages from the client for notifications
        pass

    async def notification_message(self, event):
        # Handler for messages sent to the group
        await self.send(text_data=json.dumps(event["message"]))
