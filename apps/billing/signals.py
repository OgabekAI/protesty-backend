from decimal import Decimal
import django.dispatch
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

# Custom Signals for cross-module integration (DEV 4 - Notifications, etc.)
# DEV 4 can connect receivers to these signals:
payment_completed_signal = django.dispatch.Signal()      # kwargs: payment, user, amount, payment_method
test_purchased_signal = django.dispatch.Signal()         # kwargs: purchase, user, test_id, price
subscription_created_signal = django.dispatch.Signal()   # kwargs: subscription, user, plan
promo_code_activated_signal = django.dispatch.Signal()   # kwargs: activation, user, promo_code, amount


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def handle_user_post_save(sender, instance, created, **kwargs):
    """
    Yangi user ro'yxatdan o'tganda uning uchun Balance yaratiladi
    va agar SUPER_ADMIN Registration Bonus belgilagan bo'lsa, bonus balansa tushadi.
    """
    from apps.billing.models import Balance, BillingSetting, Transaction, TransactionType

    if created:
        with transaction.atomic():
            balance, _ = Balance.objects.get_or_create(user=instance, defaults={'amount': Decimal('0.00')})
            bonus_amount = BillingSetting.get_registration_bonus()

            if bonus_amount > 0:
                balance_before = balance.amount
                balance_after = balance_before + bonus_amount
                balance.amount = balance_after
                balance.save(update_fields=['amount', 'updated_at'])

                formatted_bonus = f"{bonus_amount:,.0f}".replace(',', ' ')
                Transaction.objects.create(
                    user=instance,
                    transaction_type=TransactionType.REGISTRATION_BONUS,
                    amount=bonus_amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    description=f"+{formatted_bonus} UZS — Registration bonus",
                    metadata={'bonus_type': 'registration'}
                )
    else:
        # Agar user mavjud bo'lsa, lekin negadir balansi bo'lmasa xavfsiz yaratish
        Balance.objects.get_or_create(user=instance, defaults={'amount': Decimal('0.00')})
