from django.contrib import admin
from apps.billing.models import (
    Balance,
    BillingSetting,
    Payment,
    PromoCode,
    PromoCodeActivation,
    Purchase,
    Subscription,
    SubscriptionPlan,
    Transaction,
)
from apps.billing.services import BillingService


@admin.register(Balance)
class BalanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'created_at', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'transaction_type',
        'amount',
        'balance_before',
        'balance_after',
        'status',
        'created_at'
    )
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('user__username', 'user__email', 'description', 'reference_id')
    readonly_fields = (
        'user',
        'transaction_type',
        'amount',
        'balance_before',
        'balance_after',
        'description',
        'status',
        'reference_id',
        'metadata',
        'created_at'
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'amount',
        'payment_method',
        'status',
        'created_at',
        'completed_at'
    )
    list_filter = ('payment_method', 'status', 'created_at')
    search_fields = ('id', 'user__username', 'user__email', 'provider_transaction_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'completed_at')
    actions = ['approve_payments']

    @admin.action(description="Tanlangan to‘lovlarni tasdiqlash va balansga o‘tkazish")
    def approve_payments(self, request, queryset):
        count = 0
        for payment in queryset:
            if payment.status != 'COMPLETED':
                BillingService.complete_payment(
                    payment_id=payment.id,
                    admin_notes=f"Admin ({request.user}) tomonidan tasdiqlandi"
                )
                count += 1
        self.message_user(request, f"{count} ta to‘lov muvaffaqiyatli tasdiqlandi.")


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'amount',
        'activations_count',
        'activation_limit',
        'is_active',
        'valid_until',
        'created_by',
        'created_at'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('code',)
    readonly_fields = ('activations_count', 'created_at', 'updated_at')


@admin.register(PromoCodeActivation)
class PromoCodeActivationAdmin(admin.ModelAdmin):
    list_display = ('promo_code', 'user', 'amount_received', 'activated_at')
    list_filter = ('activated_at',)
    search_fields = ('promo_code__code', 'user__username', 'user__email')
    readonly_fields = ('promo_code', 'user', 'amount_received', 'activated_at')


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'test_id', 'price', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email', 'test_id')
    readonly_fields = ('created_at',)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_days', 'price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'plan', 'start_date', 'end_date', 'status', 'price_paid', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BillingSetting)
class BillingSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description', 'updated_at')
    search_fields = ('key', 'description')
    readonly_fields = ('updated_at',)
