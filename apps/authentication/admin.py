from django.contrib import admin
from .models import TelegramLoginCode, TelegramBotUser


@admin.register(TelegramBotUser)
class TelegramBotUserAdmin(admin.ModelAdmin):
    list_display = (
        'telegram_id',
        'first_name',
        'username',
        'is_active',
        'created_at',
        'updated_at',
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('telegram_id', 'first_name', 'username')
    ordering = ('-created_at',)


@admin.register(TelegramLoginCode)
class TelegramLoginCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'telegram_id',
        'telegram_first_name',
        'attempts',
        'is_used',
        'created_at',
        'expires_at',
    )
    list_filter = ('is_used', 'created_at')
    search_fields = ('telegram_id', 'telegram_first_name', 'code')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'expires_at')
