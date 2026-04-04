from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField
from django.conf import settings
from django.utils import timezone
import hashlib
import uuid

# Create your models here.
class UserManager(BaseUserManager):
    def create_user(self, display_name, password=None, access_key=None, **extra_fields):
        if not display_name:
            raise ValueError('Display name is required')

        # Django management commands pass "password"; API callers can pass "access_key".
        if access_key is None:
            access_key = password

        if not access_key:
            raise ValueError('Access key is required')

        user = self.model(
            display_name=display_name,
            key_hash=self.hash_key(access_key),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, display_name, password=None, access_key=None, **extra_fields):
        extra_fields.setdefault('role', User.ROLE_SUPERUSER)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(
            display_name=display_name,
            password=password,
            access_key=access_key,
            **extra_fields,
        )
    
    @staticmethod
    def hash_key(key):
        """Hash the access key using SHA-256"""
        return hashlib.sha256(key.encode()).hexdigest()

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_SUPERUSER = 'superuser'
    ROLE_ADMIN = 'admin'
    ROLE_MODERATOR = 'moderator'
    ROLE_NORMAL = 'normal'
    ROLE_SUSPENDED = 'suspended'

    ROLE_CHOICES = [
        (ROLE_SUPERUSER, 'Superuser'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MODERATOR, 'Moderator'),
        (ROLE_NORMAL, 'Normal'),
        (ROLE_SUSPENDED, 'Suspended'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    key_hash = models.CharField(max_length=64, unique=True)  # SHA-256 hash

    display_name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    bio = models.TextField(blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_NORMAL)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'display_name'
    REQUIRED_FIELDS = []
    
    def __str__(self):
        return self.display_name
    
    def check_key(self, raw_key):
        """Verify the access key"""
        return self.key_hash == UserManager.hash_key(raw_key)

    def can_moderate_posts(self):
        return self.role in {
            self.ROLE_SUPERUSER,
            self.ROLE_ADMIN,
            self.ROLE_MODERATOR,
        }

    def can_create_communities(self):
        return self.role in {
            self.ROLE_SUPERUSER,
            self.ROLE_ADMIN,
        }
    
    def can_delete_communities(self):
        return self.role in {
            self.ROLE_SUPERUSER,
        }

class Community(models.Model):
    name_validator = RegexValidator(
        regex=r'^[a-z0-9_]{2,32}$',
        message='Community name must be 2-32 chars: lowercase letters, numbers, underscore.',
    )

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=120)
    name = models.CharField(max_length=32, unique=True, validators=[name_validator], help_text='Unique identifier used in URLs. 2-32 chars: lowercase letters, numbers, underscore. eg. /[name]')
    description = models.TextField(blank=True)
    rules = JSONField(default=list, blank=True, help_text='List of community rules (array of strings).')
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_communities',
        limit_choices_to={
            'role__in': [User.ROLE_SUPERUSER, User.ROLE_ADMIN]
        }
    )
    adult_content = models.BooleanField(default=False, help_text='Whether the community contains adult content. Registered users can access adult communities, hidden from unregistered users.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Communities'

    def clean(self):
        if self.created_by and not self.created_by.can_create_communities():
            raise ValidationError('Only admin or superuser can create communities.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"/{self.name} - {self.title}"

def thread_image_upload_path(instance, filename):
    # Store images in media/threads/<thread_id>/<filename>
    return f"threads/{instance.id or 'new'}/{filename}"

STATUS_PUBLIC = 'public'
STATUS_PLATFORM_VIOLATION = 'platform_violation'
STATUS_COMMUNITY_VIOLATION = 'community_violation'
STATUS_REMOVED_BY_USER = 'removed_by_user'
STATUS_REMOVED_BY_MOD = 'removed_by_mod'

STATUS_CHOICES = [
    (STATUS_PUBLIC, 'Public'),
    (STATUS_PLATFORM_VIOLATION, 'Platform Rules Violation'),
    (STATUS_COMMUNITY_VIOLATION, 'Community Rules Violation'),
    (STATUS_REMOVED_BY_USER, 'Removed by User'),
    (STATUS_REMOVED_BY_MOD, 'Removed by Moderator'),
]

class Thread(models.Model):
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='threads',
        help_text='Community this thread belongs to.'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='threads',
        help_text='User who created the thread.'
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to=thread_image_upload_path, blank=True, null=True)
    adult_content = models.BooleanField(default=False, help_text='Hide from not logged in users if true.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_PUBLIC,
        help_text='Moderation status of the thread.'
    )
    removal_reason = models.TextField(blank=True, help_text='Reason for removal by moderator or user.')
    is_locked = models.BooleanField(default=False, help_text='If true, no new replies can be added.')
    is_deleted = models.BooleanField(default=False, help_text='Soft delete flag.')

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        # Require at least one of title or description
        if not self.title and not self.description:
            raise ValidationError('Either title or description is required.')
        if self.title == '' and self.description == '':
            raise ValidationError('Either title or description is required.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title or self.description[:30] or '[No Title]'} (/{self.community.name})"


class Reply(models.Model):
    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name='replies',
        help_text='Thread this reply belongs to.'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies',
        help_text='User who wrote the reply.'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_PUBLIC,
        help_text='Moderation status of the reply.'
    )
    removal_reason = models.TextField(blank=True, help_text='Reason for removal by moderator or user.')
    is_deleted = models.BooleanField(default=False, help_text='Soft delete flag.')
    is_edited = models.BooleanField(default=False, help_text='True if reply was edited after creation.')

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Replies'

    def save(self, *args, **kwargs):
        if self.pk and 'update_fields' in kwargs and 'content' in kwargs['update_fields']:
            self.is_edited = True
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Reply by {self.author or 'anon'} on {self.thread}"