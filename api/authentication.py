from rest_framework import authentication
from rest_framework import exceptions

from .models import User, UserManager

class AccessKeyAuthentication(authentication.BaseAuthentication):
    """Authenticate users exclusively through the X-Access-Key header."""

    def authenticate(self, request):
        access_key = request.headers.get("X-Access-Key")
        if not access_key:
            return None

        key_hash = UserManager.hash_key(access_key)
        try:
            user = User.objects.get(key_hash=key_hash, is_active=True)
        except User.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid access key") from exc

        return (user, None)
