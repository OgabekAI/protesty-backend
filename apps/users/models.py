import random
import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserRole(models.TextChoices):
    USER = 'USER', 'User'
    CONTENT_MANAGER = 'CONTENT_MANAGER', 'Content Manager'
    ADMIN = 'ADMIN', 'Admin'
    SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'


class UserStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    BLOCKED = 'BLOCKED', 'Blocked'


class Language(models.TextChoices):
    UZ = 'UZ', 'Uzbek'
    RU = 'RU', 'Russian'
    EN = 'EN', 'English'


class Gender(models.TextChoices):
    MALE = 'MALE', 'Male'
    FEMALE = 'FEMALE', 'Female'
    OTHER = 'OTHER', 'Other'


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Subject'
        verbose_name_plural = 'Subjects'

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        if not username and not email:
            username = f"user_{uuid.uuid4().hex[:8]}"

        extra_fields.setdefault('role', UserRole.USER)
        extra_fields.setdefault('status', UserStatus.ACTIVE)

        user = self.model(username=username, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.SUPER_ADMIN)
        extra_fields.setdefault('status', UserStatus.ACTIVE)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username=username, email=email, password=password, **extra_fields)


def generate_9_digit_id():
    """Generates a unique 9-digit numeric ID (100,000,000 to 999,999,999)."""
    return random.randint(100000000, 999999999)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.BigIntegerField(primary_key=True, default=generate_9_digit_id, editable=False)
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)

    # Profile fields (all optional)
    first_name = models.CharField(max_length=150, blank=True, default='')
    last_name = models.CharField(max_length=150, blank=True, default='')
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, null=True, blank=True)
    region = models.CharField(max_length=100, blank=True, default='')
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.UZ)

    # Status & Role
    status = models.CharField(max_length=15, choices=UserStatus.choices, default=UserStatus.ACTIVE)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.USER)

    # Social Auth & Accounts Linking
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    telegram_first_name = models.CharField(max_length=255, blank=True, default='')

    # Profile picture URL (saved from Google picture or Telegram photo)
    avatar = models.URLField(max_length=500, null=True, blank=True)

    # Prepared Subjects
    prepared_subjects = models.ManyToManyField(Subject, related_name='users', blank=True)

    # Permissions & Django Admin flags
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        if full_name:
            return f"{full_name} ({self.id})"
        if self.telegram_first_name:
            return f"{self.telegram_first_name} ({self.id})"
        if self.username:
            return f"{self.username} ({self.id})"
        return str(self.id)
