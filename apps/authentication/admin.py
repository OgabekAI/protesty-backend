from django.contrib import admin
from .models import TelegramLoginCode


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
