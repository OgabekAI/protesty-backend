from datetime import timedelta
import random
import uuid
from django.db import models
from django.utils import timezone


def generate_6_digit_code():
    return f"{random.randint(100000, 999999)}"


class TelegramLoginCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    telegram_id = models.BigIntegerField(db_index=True)
    telegram_first_name = models.CharField(max_length=255, blank=True, default='')
    telegram_photo_url = models.URLField(max_length=500, null=True, blank=True)
    code = models.CharField(max_length=6, default=generate_6_digit_code)

    attempts = models.IntegerField(default=0)
    is_used = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Telegram Login Code'
        verbose_name_plural = 'Telegram Login Codes'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=5)

        if self._state.adding:
            # Invalidate all previous unused codes for this telegram_id
            TelegramLoginCode.objects.filter(
                telegram_id=self.telegram_id,
                is_used=False
            ).update(is_used=True)

        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        """Checks if code is active, under 5 attempts limit, and not expired."""
        if self.is_used:
            return False
        if self.attempts >= 5:
            return False
        if timezone.now() >= self.expires_at:
            return False
        return True

    def increment_attempts(self):
        self.attempts += 1
        if self.attempts >= 5:
            self.is_used = True
        self.save(update_fields=['attempts', 'is_used'])

    def __str__(self):
        return f"Code {self.code} for Telegram ID {self.telegram_id}"
