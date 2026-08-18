import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TransactionType(models.TextChoices):
    DEPOSIT = 'DEPOSIT', 'Balance to‘ldirildi'
    TEST_PURCHASE = 'TEST_PURCHASE', 'Test sotib olindi'
    SUBSCRIPTION = 'SUBSCRIPTION', 'Subscription sotib olindi'
    REGISTRATION_BONUS = 'REGISTRATION_BONUS', 'Registration bonus'
    PROMO_CODE = 'PROMO_CODE', 'Promo code faollashtirildi'
    ADMIN_CREDIT = 'ADMIN_CREDIT', 'Admin tomonidan to‘ldirildi'
    ADMIN_DEBIT = 'ADMIN_DEBIT', 'Admin tomonidan yechildi'
    REFUND = 'REFUND', 'To‘lov qaytarildi'


class TransactionStatus(models.TextChoices):
    SUCCESS = 'SUCCESS', 'Muvaffaqiyatli'
    PENDING = 'PENDING', 'Kutilmoqda'
    FAILED = 'FAILED', 'Xatolik yuz berdi'
    CANCELLED = 'CANCELLED', 'Bekor qilindi'


class PaymentMethod(models.TextChoices):
    CLICK = 'CLICK', 'Click'
    PAYME = 'PAYME', 'Payme'
    TRANSFER = 'TRANSFER', 'Transfer (Bank o‘tkazmasi)'


class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Kutilmoqda'
    COMPLETED = 'COMPLETED', 'Muvaffaqiyatli to‘landi'
    FAILED = 'FAILED', 'To‘lov amalga oshmadi'
    CANCELLED = 'CANCELLED', 'Bekor qilindi'


class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Faol'
    EXPIRED = 'EXPIRED', 'Muddati tugagan'
    CANCELLED = 'CANCELLED', 'Bekor qilingan'


class Balance(models.Model):
    """
    Har bir foydalanuvchining hisob balansi.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='balance',
        verbose_name="Foydalanuvchi"
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Balans summasi (UZS)"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="O‘zgartirilgan vaqt")

    class Meta:
        verbose_name = "Balans"
        verbose_name_plural = "Balanslar"

    def __str__(self):
        return f"{self.user} - {self.amount} UZS"


class Transaction(models.Model):
    """
    Balans o'zgarishi tarixi (audit log).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='billing_transactions',
        verbose_name="Foydalanuvchi"
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionType.choices,
        verbose_name="Tranzaksiya turi"
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Summa (UZS)"
    )
    balance_before = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Oldingi balans"
    )
    balance_after = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Keyingi balans"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Tavsif"
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.SUCCESS,
        verbose_name="Holat"
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Bog‘liq ID (Payment/Purchase/Promo/Admin)"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Qo‘shimcha ma'lumotlar"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Amal bajarilgan vaqt"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Tranzaksiya"
        verbose_name_plural = "Tranzaksiyalar"

    def __str__(self):
        sign = "+" if self.transaction_type in [
            TransactionType.DEPOSIT,
            TransactionType.REGISTRATION_BONUS,
            TransactionType.PROMO_CODE,
            TransactionType.ADMIN_CREDIT,
            TransactionType.REFUND
        ] else "-"
        return f"{sign}{self.amount} UZS — {self.get_transaction_type_display()} ({self.user})"


class Payment(models.Model):
    """
    To‘lovlar (Click, Payme, Transfer).
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="To‘lov ID"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name="Foydalanuvchi"
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('100.00'))],
        verbose_name="To‘lov summasi (UZS)"
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        verbose_name="To‘lov usuli"
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name="To‘lov holati"
    )
    provider_transaction_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Provider tranzaksiya ID (Click / Payme)"
    )
    proof_image = models.FileField(
        upload_to='payments/proofs/',
        blank=True,
        null=True,
        verbose_name="Bank cheki rasmi / hujjati"
    )
    admin_notes = models.TextField(
        blank=True,
        verbose_name="Admin izohi (tasdiqlash yoki rad etish sababi)"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Qo‘shimcha parametrlar"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqt")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="To‘langan vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "To‘lov"
        verbose_name_plural = "To‘lovlar"

    def __str__(self):
        return f"Payment #{self.id} - {self.amount} UZS ({self.get_payment_method_display()}) [{self.status}]"


class PromoCode(models.Model):
    """
    SUPER_ADMIN / ADMIN yaratadigan promokodlar.
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Promokod"
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))],
        verbose_name="Beriladigan balans summasi (UZS)"
    )
    activation_limit = models.PositiveIntegerField(
        default=1,
        verbose_name="Maksimal aktivatsiyalar soni"
    )
    activations_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Ishlatilgan aktivatsiyalar soni"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Faolmi?"
    )
    valid_from = models.DateTimeField(
        default=timezone.now,
        verbose_name="Amal qilish boshlanishi"
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Amal qilish muddati (tugash sanasi)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_promo_codes',
        verbose_name="Yaratgan admin"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Promokod"
        verbose_name_plural = "Promokodlar"

    def __str__(self):
        return f"{self.code} - {self.amount} UZS ({self.activations_count}/{self.activation_limit})"

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.activations_count >= self.activation_limit:
            return False
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True


class PromoCodeActivation(models.Model):
    """
    Foydalanuvchi tomonidan promokodning faollashtirilishi.
    Bitta user bitta promokodni faqat 1 marta ishlata oladi.
    """
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.CASCADE,
        related_name='activations',
        verbose_name="Promokod"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='promo_code_activations',
        verbose_name="Foydalanuvchi"
    )
    amount_received = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Olingan summa (UZS)"
    )
    activated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Faollashtirilgan vaqt"
    )

    class Meta:
        ordering = ['-activated_at']
        unique_together = ('promo_code', 'user')
        verbose_name = "Promokod faollashtiruvi"
        verbose_name_plural = "Promokod faollashtiruvlari"

    def __str__(self):
        return f"{self.user} -> {self.promo_code.code} (+{self.amount_received} UZS)"


class Purchase(models.Model):
    """
    Alohida testni sotib olish yozuvi.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='purchases',
        verbose_name="Foydalanuvchi"
    )
    test_id = models.PositiveBigIntegerField(
        db_index=True,
        verbose_name="Test ID"
    )
    price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="To‘langan narx (UZS)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Sotib olingan vaqt"
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'test_id')
        verbose_name = "Test xaridi"
        verbose_name_plural = "Test xaridlari"

    def __str__(self):
        return f"{self.user} - Test #{self.test_id} ({self.price} UZS)"


class SubscriptionPlan(models.Model):
    """
    Obuna rejalari (masalan, Oylik / 30 kunlik).
    """
    name = models.CharField(
        max_length=100,
        default="Oylik obuna",
        verbose_name="Obuna nomi"
    )
    duration_days = models.PositiveIntegerField(
        default=30,
        verbose_name="Davomiyligi (kun)"
    )
    price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('50000.00'),
        verbose_name="Narxi (UZS)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Faolmi?"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Tavsif"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']
        verbose_name = "Obuna rejasi"
        verbose_name_plural = "Obuna rejalari"

    def __str__(self):
        return f"{self.name} - {self.price} UZS / {self.duration_days} kun"


class Subscription(models.Model):
    """
    Foydalanuvchining obunasi.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name="Foydalanuvchi"
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_subscriptions',
        verbose_name="Obuna rejasi"
    )
    start_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="Boshlanish sanasi"
    )
    end_date = models.DateTimeField(
        verbose_name="Tugash sanasi"
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        verbose_name="Holat"
    )
    price_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="To‘langan narx (UZS)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Obuna"
        verbose_name_plural = "Obunalar"

    def __str__(self):
        return f"{self.user} - Obuna ({self.status}) -> {self.end_date.strftime('%Y-%m-%d %H:%M')}"

    @property
    def is_active_now(self):
        return self.status == SubscriptionStatus.ACTIVE and self.end_date > timezone.now()


class BillingSetting(models.Model):
    """
    SUPER_ADMIN tomonidan belgilanadigan billing tizim sozlamalari
    (Masalan: REGISTRATION_BONUS, DEFAULT_SUBSCRIPTION_PRICE).
    """
    key = models.CharField(
        max_length=100,
        primary_key=True,
        verbose_name="Sozlama kaliti"
    )
    value = models.TextField(
        verbose_name="Qiymat"
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Tavsif"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Billing sozlamasi"
        verbose_name_plural = "Billing sozlamalari"

    def __str__(self):
        return f"{self.key}: {self.value}"

    @classmethod
    def get_setting(cls, key: str, default: str = "") -> str:
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_setting(cls, key: str, value: str, description: str = ""):
        cls.objects.update_or_create(
            key=key,
            defaults={'value': str(value), 'description': description}
        )

    @classmethod
    def get_registration_bonus(cls) -> Decimal:
        val = cls.get_setting("REGISTRATION_BONUS", "0")
        try:
            return Decimal(val)
        except Exception:
            return Decimal("0.00")

    @classmethod
    def set_registration_bonus(cls, amount: Decimal):
        cls.set_setting("REGISTRATION_BONUS", str(amount), "Yangi ro‘yxatdan o‘tgan userlar uchun bonus miqdori")
