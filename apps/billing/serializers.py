from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.billing.models import (
    Balance,
    BillingSetting,
    Payment,
    PaymentMethod,
    PaymentStatus,
    PromoCode,
    PromoCodeActivation,
    Purchase,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    Transaction,
)

User = get_user_model()


class BalanceSerializer(serializers.ModelSerializer):
    """
    Foydalanuvchi balansi va faol obunasi haqida to'liq ma'lumot.
    """
    has_active_subscription = serializers.SerializerMethodField()
    active_subscription_end_date = serializers.SerializerMethodField()

    class Meta:
        model = Balance
        fields = [
            'id',
            'amount',
            'has_active_subscription',
            'active_subscription_end_date',
            'updated_at',
        ]
        read_only_fields = fields

    def get_has_active_subscription(self, obj) -> bool:
        return Subscription.objects.filter(
            user=obj.user,
            status=SubscriptionStatus.ACTIVE,
            end_date__gt=timezone.now()
        ).exists()

    def get_active_subscription_end_date(self, obj):
        active_sub = Subscription.objects.filter(
            user=obj.user,
            status=SubscriptionStatus.ACTIVE,
            end_date__gt=timezone.now()
        ).order_by('-end_date').first()
        return active_sub.end_date.isoformat() if active_sub else None


class TransactionSerializer(serializers.ModelSerializer):
    """
    Balans tarixi va tranzaksiyalar.
    """
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_type',
            'transaction_type_display',
            'amount',
            'balance_before',
            'balance_after',
            'description',
            'status',
            'status_display',
            'reference_id',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields


class PaymentCreateSerializer(serializers.Serializer):
    """
    To'lov yaratish uchun serializer (Click, Payme, Transfer).
    """
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('1000.00'),
        help_text="To‘lov summasi (kamida 1 000 UZS)"
    )
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices,
        help_text="CLICK, PAYME yoki TRANSFER"
    )
    metadata = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Ixtiyoriy qo‘shimcha parametrlar"
    )


class PaymentSerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    checkout_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'amount',
            'payment_method',
            'payment_method_display',
            'status',
            'status_display',
            'provider_transaction_id',
            'proof_image',
            'admin_notes',
            'checkout_url',
            'created_at',
            'completed_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'status_display',
            'provider_transaction_id',
            'checkout_url',
            'created_at',
            'completed_at',
        ]

    def get_checkout_url(self, obj) -> str:
        """
        Click va Payme uchun to'lov URL generatsiya qiladi.
        """
        if obj.payment_method == PaymentMethod.CLICK:
            # Click URL formati
            service_id = "TEST_SERVICE_ID"
            merchant_id = "TEST_MERCHANT_ID"
            return f"https://my.click.uz/services/pay?service_id={service_id}&merchant_id={merchant_id}&amount={obj.amount}&transaction_param={obj.id}"
        elif obj.payment_method == PaymentMethod.PAYME:
            # Payme URL formati
            merchant_id = "TEST_PAYME_MERCHANT_ID"
            amount_tiyin = int(obj.amount * 100)
            return f"https://checkout.paycom.uz/checkout?merchant={merchant_id}&amount={amount_tiyin}&account[order_id]={obj.id}"
        return ""


class TransferProofSerializer(serializers.ModelSerializer):
    """
    Bank o'tkazmasi (TRANSFER) uchun chek rasmini yuklash.
    """
    class Meta:
        model = Payment
        fields = ['proof_image', 'admin_notes']


class PurchaseCreateSerializer(serializers.Serializer):
    """
    Test sotib olish.
    """
    test_id = serializers.IntegerField(
        min_value=1,
        help_text="Sotib olinadigan test ID raqami"
    )
    price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Agar test narxi DEV 2 modelsiz test qilinsa narxni qo‘lda berish mumkin"
    )


class PurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purchase
        fields = ['id', 'test_id', 'price', 'created_at']
        read_only_fields = fields


class PurchaseCheckSerializer(serializers.Serializer):
    test_id = serializers.IntegerField()
    has_access = serializers.BooleanField()
    access_type = serializers.CharField()
    has_purchased_directly = serializers.BooleanField()
    has_active_subscription = serializers.BooleanField()



class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'duration_days', 'price', 'is_active', 'description']


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    is_active_now = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id',
            'plan',
            'plan_name',
            'start_date',
            'end_date',
            'status',
            'price_paid',
            'is_active_now',
            'created_at',
        ]
        read_only_fields = fields


class SubscriptionPurchaseSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Ixtiyoriy reja ID (agar berilmasa faol standart oylik reja olinadi)"
    )


class PromoCodeActivateSerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=50,
        help_text="Aktivatsiya qilinadigan promokod"
    )


class PromoCodeAdminSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = PromoCode
        fields = [
            'id',
            'code',
            'amount',
            'activation_limit',
            'activations_count',
            'is_active',
            'valid_from',
            'valid_until',
            'is_valid',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'activations_count', 'is_valid', 'created_by', 'created_at', 'updated_at']

    def validate_code(self, value):
        return value.strip().upper()


class AdminBalanceAdjustSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(
        help_text="Foydalanuvchi ID raqami"
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Qo‘shiladigan (+) yoki yechiladigan (-) summa"
    )
    reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="Balans o‘zgarishi sababi"
    )


class BillingSettingSerializer(serializers.Serializer):
    registration_bonus = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.00'),
        help_text="Yangi foydalanuvchilar uchun registratsiya bonusi (UZS)"
    )
    default_subscription_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.00'),
        required=False,
        help_text="Oylik obunaning standart narxi (UZS)"
    )
