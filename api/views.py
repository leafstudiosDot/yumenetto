from .models import Community, Thread, Reply, STATUS_PUBLIC

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
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


class RefreshJWTView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token required.'}, status=400)

        try:
            refresh = RefreshToken(refresh_token)
            access = str(refresh.access_token)
        except TokenError:
            return Response({'detail': 'Refresh token is invalid or expired.'}, status=401)

        return Response({'access': access})

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

def _community_forum_tables(community):
    qn = connection.ops.quote_name
    schema = qn(community.schema_name)
    return f"{schema}.{qn('threads')}", f"{schema}.{qn('replies')}"

@api_view(['GET', 'POST'])
def community_threads(request, name):
    community = get_object_or_404(Community, name=name)

    if request.method == 'POST':
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        title = (request.data.get('title') or '').strip()
        description = (request.data.get('description') or '').strip()

        if not title and not description:
            return Response(
                {'detail': 'Either title or description is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if connection.vendor != 'postgresql':
            thread = Thread.objects.create(
                community=community,
                author=request.user,
                title=title,
                description=description,
            )
            return Response(
                {
                    'id': thread.id,
                    'title': thread.title,
                    'description': thread.description,
                    'author': thread.author.display_name if thread.author else 'deleted-user',
                    'created_at': thread.created_at,
                    'reply_count': 0,
                },
                status=status.HTTP_201_CREATED,
            )

        if not community.schema_name:
            return Response({'detail': 'Community schema is not configured.'}, status=500)

        thread_table, _ = _community_forum_tables(community)
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {thread_table} (community_id, author_id, title, description)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, description, created_at
                """,
                [community.id, request.user.id, title, description],
            )
            created_row = cursor.fetchone()

        return Response(
            {
                'id': created_row[0],
                'title': created_row[1],
                'description': created_row[2],
                'created_at': created_row[3],
                'author': request.user.display_name,
                'reply_count': 0,
            },
            status=status.HTTP_201_CREATED,
        )

    if connection.vendor != 'postgresql':
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

    if not community.schema_name:
        return Response({'detail': 'Community schema is not configured.'}, status=500)

    thread_table, reply_table = _community_forum_tables(community)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                t.id,
                t.title,
                t.description,
                t.created_at,
                COALESCE(u.display_name, 'deleted-user') AS author,
                COUNT(r.id) FILTER (WHERE r.status = %s AND r.is_deleted = FALSE) AS reply_count
            FROM {thread_table} t
            LEFT JOIN {reply_table} r ON r.thread_id = t.id
            LEFT JOIN api_user u ON u.id = t.author_id
            WHERE t.community_id = %s
              AND t.status = %s
              AND t.is_deleted = FALSE
            GROUP BY t.id, t.title, t.description, t.created_at, u.display_name
            ORDER BY t.created_at DESC
            """,
            [STATUS_PUBLIC, community.id, STATUS_PUBLIC],
        )
        rows = cursor.fetchall()

    return Response({
        'community': {
            'name': community.name,
            'title': community.title,
            'description': community.description,
        },
        'threads': [
            {
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'created_at': row[3],
                'author': row[4],
                'reply_count': row[5],
            }
            for row in rows
        ],
    })

@api_view(['GET', 'POST'])
def thread_detail(request, name, thread_id):
    community = get_object_or_404(Community, name=name)

    if request.method == 'POST':
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        content = (request.data.get('content') or '').strip()
        if not content:
            return Response({'detail': 'Reply content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if connection.vendor != 'postgresql':
            thread = get_object_or_404(
                Thread,
                id=thread_id,
                community=community,
                status=STATUS_PUBLIC,
                is_deleted=False,
            )
            if thread.is_locked:
                return Response({'detail': 'This thread is locked.'}, status=status.HTTP_400_BAD_REQUEST)

            reply = Reply.objects.create(thread=thread, author=request.user, content=content)
            thread.last_activity = reply.created_at
            thread.save(update_fields=['last_activity', 'updated_at'])

            return Response(
                {
                    'id': reply.id,
                    'content': reply.content,
                    'author': reply.author.display_name if reply.author else 'deleted-user',
                    'created_at': reply.created_at,
                },
                status=status.HTTP_201_CREATED,
            )

        if not community.schema_name:
            return Response({'detail': 'Community schema is not configured.'}, status=500)

        thread_table, reply_table = _community_forum_tables(community)

        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT is_locked
                FROM {thread_table}
                WHERE id = %s
                  AND community_id = %s
                  AND status = %s
                  AND is_deleted = FALSE
                LIMIT 1
                """,
                [thread_id, community.id, STATUS_PUBLIC],
            )
            thread_row = cursor.fetchone()

            if not thread_row:
                raise Http404

            if thread_row[0]:
                return Response({'detail': 'This thread is locked.'}, status=status.HTTP_400_BAD_REQUEST)

            cursor.execute(
                f"""
                INSERT INTO {reply_table} (thread_id, author_id, content)
                VALUES (%s, %s, %s)
                RETURNING id, content, created_at
                """,
                [thread_id, request.user.id, content],
            )
            reply_row = cursor.fetchone()

            cursor.execute(
                f"""
                UPDATE {thread_table}
                SET last_activity = NOW(), updated_at = NOW()
                WHERE id = %s
                """,
                [thread_id],
            )

        return Response(
            {
                'id': reply_row[0],
                'content': reply_row[1],
                'created_at': reply_row[2],
                'author': request.user.display_name,
            },
            status=status.HTTP_201_CREATED,
        )

    if connection.vendor != 'postgresql':
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

    if not community.schema_name:
        return Response({'detail': 'Community schema is not configured.'}, status=500)

    thread_table, reply_table = _community_forum_tables(community)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                t.id,
                t.title,
                t.description,
                t.created_at,
                COALESCE(u.display_name, 'deleted-user') AS author
            FROM {thread_table} t
            LEFT JOIN api_user u ON u.id = t.author_id
            WHERE t.id = %s
              AND t.community_id = %s
              AND t.status = %s
              AND t.is_deleted = FALSE
            LIMIT 1
            """,
            [thread_id, community.id, STATUS_PUBLIC],
        )
        thread_row = cursor.fetchone()

        if not thread_row:
            raise Http404

        cursor.execute(
            f"""
            SELECT
                r.id,
                r.content,
                r.created_at,
                COALESCE(u.display_name, 'deleted-user') AS author
            FROM {reply_table} r
            LEFT JOIN api_user u ON u.id = r.author_id
            WHERE r.thread_id = %s
              AND r.status = %s
              AND r.is_deleted = FALSE
            ORDER BY r.created_at ASC
            """,
            [thread_id, STATUS_PUBLIC],
        )
        reply_rows = cursor.fetchall()

    return Response({
        'community': {
            'name': community.name,
            'title': community.title,
        },
        'thread': {
            'id': thread_row[0],
            'title': thread_row[1],
            'description': thread_row[2],
            'created_at': thread_row[3],
            'author': thread_row[4],
        },
        'replies': [
            {
                'id': row[0],
                'content': row[1],
                'created_at': row[2],
                'author': row[3],
            }
            for row in reply_rows
        ],
    })