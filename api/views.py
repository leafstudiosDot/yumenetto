from .models import Community, Thread, Reply, STATUS_PUBLIC

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
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

@api_view(['GET'])
def community_list(request):
    communities = Community.objects.all().order_by('name')
    data = [
        {
            'name': c.name,
            'title': c.title,
            'description': c.description,
            'adult_content': c.adult_content,
        }
        for c in communities
    ]
    return Response(data)


@api_view(['GET'])
def community_threads(request, name):
    community = get_object_or_404(Community, name=name)
    threads = (
        Thread.objects
        .filter(community=community, status=STATUS_PUBLIC, is_deleted=False)
        .select_related('author')
        .annotate(
            reply_count=Count(
                'replies',
                filter=Q(replies__status=STATUS_PUBLIC, replies__is_deleted=False),
            )
        )
        .order_by('-created_at')
    )

    return Response({
        'community': {
            'name': community.name,
            'title': community.title,
            'description': community.description,
        },
        'threads': [
            {
                'id': t.id,
                'title': t.title,
                'description': t.description,
                'author': t.author.display_name if t.author else 'deleted-user',
                'created_at': t.created_at,
                'reply_count': t.reply_count,
            }
            for t in threads
        ],
    })


@api_view(['GET'])
def thread_detail(request, name, thread_id):
    community = get_object_or_404(Community, name=name)
    thread = get_object_or_404(
        Thread.objects.select_related('author', 'community'),
        id=thread_id,
        community=community,
        status=STATUS_PUBLIC,
        is_deleted=False,
    )

    replies = (
        Reply.objects
        .filter(thread=thread, status=STATUS_PUBLIC, is_deleted=False)
        .select_related('author')
        .order_by('created_at')
    )

    return Response({
        'community': {
            'name': community.name,
            'title': community.title,
        },
        'thread': {
            'id': thread.id,
            'title': thread.title,
            'description': thread.description,
            'author': thread.author.display_name if thread.author else 'deleted-user',
            'created_at': thread.created_at,
        },
        'replies': [
            {
                'id': reply.id,
                'content': reply.content,
                'author': reply.author.display_name if reply.author else 'deleted-user',
                'created_at': reply.created_at,
            }
            for reply in replies
        ],
    })