from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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
    name = models.CharField(max_length=32, unique=True, validators=[name_validator])
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_communities',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def clean(self):
        if self.created_by and not self.created_by.can_create_communities():
            raise ValidationError('Only admin or superuser can create communities.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"/{self.name} - {self.title}"