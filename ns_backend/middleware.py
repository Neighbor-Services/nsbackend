from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.db import close_old_connections

User = get_user_model()

@database_sync_to_async
def get_user(token_key):
    try:
        # Validate token
        access_token = AccessToken(token_key)
        user_id = access_token.payload['user_id']
        return User.objects.get(id=user_id)
    except Exception:
        return AnonymousUser()

class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Close old database connections
        close_old_connections()
        
        # Get token from headers (standard Bearer header)
        headers = dict(scope.get('headers', []))
        token_key = None
        
        auth_header = headers.get(b'authorization', b'').decode().split()
        if auth_header and len(auth_header) == 2 and auth_header[0].lower() == 'bearer':
            token_key = auth_header[1]
        
        # Fallback to query string
        if not token_key:
            query_string = scope.get('query_string', b'').decode()
            if query_string:
                try:
                    query_params = dict(qp.split('=') for qp in query_string.split('&') if '=' in qp)
                    token_key = query_params.get('token')
                except Exception:
                    pass

        if token_key:
            user = await get_user(token_key)
            scope['user'] = user
            if user.is_anonymous:
                print(f"WS Auth Failed: Invalid or expired token for path {scope.get('path')}")
            else:
                print(f"WS Auth Success: User {user.email} for path {scope.get('path')}")
        else:
            scope['user'] = AnonymousUser()
            print(f"WS Auth Failed: No token found for path {scope.get('path')}")

        return await self.inner(scope, receive, send)
