from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Subject, User, UserStatus


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('name',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'id',
        'username',
        'first_name',
        'last_name',
        'role',
        'status',
        'language',
        'google_id',
        'telegram_id',
        'created_at',
    )
    list_filter = ('role', 'status', 'language', 'is_staff', 'is_superuser')
    search_fields = ('id', 'username', 'first_name', 'last_name', 'google_id', 'telegram_id')
    ordering = ('-created_at',)

    fieldsets = (
        ('Authentication', {'fields': ('username', 'password')}),
        ('Personal Info', {
            'fields': (
                'first_name',
                'last_name',
                'date_of_birth',
                'gender',
                'region',
                'language',
                'avatar',
                'prepared_subjects',
            )
        }),
        ('Role & Status', {'fields': ('role', 'status')}),
        ('Social Accounts', {'fields': ('google_id', 'telegram_id', 'telegram_first_name')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'is_active', 'groups', 'user_permissions')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    readonly_fields = ('created_at', 'updated_at')

    actions = ['block_users', 'unblock_users']

    @admin.action(description='Block selected users')
    def block_users(self, request, queryset):
        updated = queryset.update(status=UserStatus.BLOCKED)
        self.message_user(request, f'{updated} user(s) successfully blocked.')

    @admin.action(description='Unblock selected users')
    def unblock_users(self, request, queryset):
        updated = queryset.update(status=UserStatus.ACTIVE)
        self.message_user(request, f'{updated} user(s) successfully unblocked.')
