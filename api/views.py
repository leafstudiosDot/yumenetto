from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model
import secrets

from .authentication import AccessKeyAuthentication
from .pow import ProofOfWorkPermission

# Create your views here.
@api_view(['GET'])
def health_check(request):
    return Response({
        'status': 'ok',
        'message': 'good'
    })


# JWT login/register endpoints
class ObtainJWTView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        key = request.data.get('key')
        if not key:
            return Response({'detail': 'Key required.'}, status=400)
        User = get_user_model()
        key_hash = User.objects.hash_key(key)
        try:
            user = User.objects.get(key_hash=key_hash, is_active=True)
        except User.DoesNotExist:
            return Response({'detail': 'Invalid key.'}, status=401)
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'display_name': user.display_name,
        })

class RegisterKeyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        display_name = request.data.get('display_name')
        if not display_name:
            return Response({'detail': 'Display name required.'}, status=400)
        key = secrets.token_urlsafe(32)
        User = get_user_model()
        if User.objects.filter(display_name=display_name).exists():
            return Response({'detail': 'Display name already taken.'}, status=409)
        user = User.objects.create_user(display_name=display_name, access_key=key)
        refresh = RefreshToken.for_user(user)
        return Response({
            'key': key,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'display_name': user.display_name,
        }, status=201)

@api_view(['GET'])
def pow_config(request):
    difficulty = int(getattr(settings, 'POW_DIFFICULTY', 4))
    max_age_seconds = int(getattr(settings, 'POW_MAX_AGE_SECONDS', 120))

    return Response({
        'difficulty': difficulty,
        'max_age_seconds': max_age_seconds,
        'algorithm': 'sha256',
        'payload_format': '{key_hash}:{METHOD}:{PATH}:{TIMESTAMP}:{NONCE}',
        'headers_required': ['X-Access-Key', 'X-POW-Timestamp', 'X-POW-Nonce']
    })

@api_view(['GET'])
@authentication_classes([AccessKeyAuthentication])
@permission_classes([IsAuthenticated, ProofOfWorkPermission])
def whoami(request):
    return Response({
        'public_id': str(request.user.public_id),
        'display_name': request.user.display_name,
        'identity_mode': 'access-key-only',
        'pow_verified': True
    })