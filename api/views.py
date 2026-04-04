from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .authentication import AccessKeyAuthentication
from .pow import ProofOfWorkPermission

# Create your views here.
@api_view(['GET'])
def health_check(request):
    return Response({
        'status': 'ok',
        'message': 'good'
    })

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