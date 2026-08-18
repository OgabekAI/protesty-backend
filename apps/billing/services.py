from datetime import timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

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
    TransactionType,
    TransactionStatus,
)
from apps.billing.signals import (
    payment_completed_signal,
    test_purchased_signal,
    subscription_created_signal,
    promo_code_activated_signal,
)


class BillingService:
    """
    Billing tizimining asosiy biznes mantiq xizmati.
    Barcha pul operatsiyalari xavfsiz va atomic tranzaksiyada bajariladi.
    """

    @staticmethod
    def get_or_create_balance(user) -> Balance:
        balance, _ = Balance.objects.get_or_create(
            user=user,
            defaults={'amount': Decimal('0.00')}
        )
        return balance

    @staticmethod
    @transaction.atomic
    def create_payment(
        user,
        amount: Decimal,
        payment_method: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Payment:
        """
        Yangi to'lov yaratadi (Click, Payme yoki Transfer).
        """
        amount = Decimal(str(amount))
        if amount <= Decimal('0'):
            raise ValidationError("To‘lov summasi 0 dan katta bo‘lishi kerak.")

        payment = Payment.objects.create(
            user=user,
            amount=amount,
            payment_method=payment_method,
            status=PaymentStatus.PENDING,
            metadata=metadata or {}
        )
        return payment

    @staticmethod
    @transaction.atomic
    def complete_payment(
        payment_id,
        provider_transaction_id: Optional[str] = None,
        admin_notes: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Payment:
        """
        To'lovni muvaffaqiyatli yakunlaydi va foydalanuvchi balansiga pul qo'shadi.
        """
        payment = Payment.objects.select_for_update().get(id=payment_id)

        if payment.status == PaymentStatus.COMPLETED:
            return payment  # Idempotentlik

        user = payment.user
        balance = Balance.objects.select_for_update().get_or_create(
            user=user,
            defaults={'amount': Decimal('0.00')}
        )[0]

        balance_before = balance.amount
        balance_after = balance_before + payment.amount

        balance.amount = balance_after
        balance.save(update_fields=['amount', 'updated_at'])

        payment.status = PaymentStatus.COMPLETED
        payment.completed_at = timezone.now()
        if provider_transaction_id:
            payment.provider_transaction_id = provider_transaction_id
        if admin_notes:
            payment.admin_notes = admin_notes
        if metadata:
            payment.metadata.update(metadata)
        payment.save()

        formatted_amount = f"{payment.amount:,.0f}".replace(',', ' ')
        method_label = payment.get_payment_method_display()
        Transaction.objects.create(
            user=user,
            transaction_type=TransactionType.DEPOSIT,
            amount=payment.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"+{formatted_amount} UZS — Balance to‘ldirildi ({method_label})",
            status=TransactionStatus.SUCCESS,
            reference_id=str(payment.id),
            metadata={'payment_method': payment.payment_method, 'payment_id': str(payment.id)}
        )

        # DEV 4 uchun signal
        payment_completed_signal.send(
            sender=Payment,
            payment=payment,
            user=user,
            amount=payment.amount,
            payment_method=payment.payment_method
        )

        return payment

    @staticmethod
    @transaction.atomic
    def fail_or_cancel_payment(payment_id, status: str, admin_notes: str = "") -> Payment:
        payment = Payment.objects.select_for_update().get(id=payment_id)
        if payment.status == PaymentStatus.COMPLETED:
            raise ValidationError("Yakunlangan to‘lovni bekor qilib bo‘lmaydi.")

        payment.status = status
        if admin_notes:
            payment.admin_notes = admin_notes
        payment.save(update_fields=['status', 'admin_notes', 'updated_at'])
        return payment

    @staticmethod
    def get_test_price(test_id: int) -> Optional[Decimal]:
        """
        DEV 2 Test modelidan test narxini oladi (agar mavjud bo'lsa).
        """
        try:
            TestModel = apps.get_model('tests', 'Test', require_ready=False)
            test = TestModel.objects.get(id=test_id)
            return Decimal(str(test.price))
        except Exception:
            return None

    @staticmethod
    @transaction.atomic
    def purchase_test(user, test_id: int, override_price: Optional[Decimal] = None) -> Purchase:
        """
        Foydalanuvchi alohida testni balans orqali sotib oladi.
        """
        # 1. Oldin sotib olinganligini tekshirish
        if Purchase.objects.filter(user=user, test_id=test_id).exists():
            raise ValidationError("Ushbu test allaqachon sotib olingan.")

        # 2. Narxni aniqlash
        price = override_price
        if price is None:
            price = BillingService.get_test_price(test_id)

        if price is None:
            raise ValidationError(f"ID #{test_id} raqamli test topilmadi yoki narxi belgilanmagan.")

        price = Decimal(str(price))
        if price < Decimal('0.00'):
            raise ValidationError("Test narxi manfiy bo‘lishi mumkin emas.")

        # 3. Balansni tekshirish va yechish
        balance = Balance.objects.select_for_update().get_or_create(
            user=user,
            defaults={'amount': Decimal('0.00')}
        )[0]

        if balance.amount < price:
            formatted_bal = f"{balance.amount:,.0f}".replace(',', ' ')
            formatted_price = f"{price:,.0f}".replace(',', ' ')
            raise ValidationError(
                f"Balansda mablag‘ yetarli emas. Sizning balansingiz: {formatted_bal} UZS, Test narxi: {formatted_price} UZS."
            )

        balance_before = balance.amount
        balance_after = balance_before - price

        balance.amount = balance_after
        balance.save(update_fields=['amount', 'updated_at'])

        # 4. Xaridni saqlash
        purchase = Purchase.objects.create(
            user=user,
            test_id=test_id,
            price=price
        )

        formatted_price = f"{price:,.0f}".replace(',', ' ')
        Transaction.objects.create(
            user=user,
            transaction_type=TransactionType.TEST_PURCHASE,
            amount=price,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"-{formatted_price} UZS — Test sotib olindi (Test #{test_id})",
            status=TransactionStatus.SUCCESS,
            reference_id=str(purchase.id),
            metadata={'test_id': test_id, 'purchase_id': purchase.id}
        )

        # 5. DEV 4 uchun bildirishnoma signali
        test_purchased_signal.send(
            sender=Purchase,
            purchase=purchase,
            user=user,
            test_id=test_id,
            price=price
        )

        return purchase

    @staticmethod
    def has_user_purchased_test(user, test_id: int) -> bool:
        """
        DEV 2 yoki boshqa qismlar foydalanuvchining testga ruxsati borligini tekshirishi uchun helper.
        Agar foydalanuvchida faol oylik Subscription bo'lsa yoki testni sotib olgan bo'lsa True qaytaradi.
        """
        if not user or not user.is_authenticated:
            return False

        # 1. Alohida sotib olinganmi?
        if Purchase.objects.filter(user=user, test_id=test_id).exists():
            return True

        # 2. Faol obunasi bormi?
        active_sub = Subscription.objects.filter(
            user=user,
            status=SubscriptionStatus.ACTIVE,
            end_date__gt=timezone.now()
        ).exists()

        return active_sub

    @staticmethod
    @transaction.atomic
    def purchase_subscription(user, plan_id: Optional[int] = None) -> Subscription:
        """
        Foydalanuvchi obuna sotib oladi.
        Agar foydalanuvchida hozir ham faol obuna bo'lsa, muddati yangi rejaga muvofiq uzaytiriladi.
        """
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
            except SubscriptionPlan.DoesNotExist:
                raise ValidationError("Bunday obuna rejasi mavjud emas yoki faol emas.")
        else:
            plan = SubscriptionPlan.objects.filter(is_active=True).first()
            if not plan:
                plan = SubscriptionPlan.objects.create(
                    name="Oylik obuna",
                    duration_days=30,
                    price=Decimal('50000.00'),
                    is_active=True
                )

        price = plan.price
        duration_days = plan.duration_days

        balance = Balance.objects.select_for_update().get_or_create(
            user=user,
            defaults={'amount': Decimal('0.00')}
        )[0]

        if balance.amount < price:
            formatted_bal = f"{balance.amount:,.0f}".replace(',', ' ')
            formatted_price = f"{price:,.0f}".replace(',', ' ')
            raise ValidationError(
                f"Balansda mablag‘ yetarli emas. Balansingiz: {formatted_bal} UZS, Obuna narxi: {formatted_price} UZS."
            )

        balance_before = balance.amount
        balance_after = balance_before - price

        balance.amount = balance_after
        balance.save(update_fields=['amount', 'updated_at'])

        # Amaldagi faol obunani tekshirish (uzaytirish uchun)
        now = timezone.now()
        active_sub = Subscription.objects.filter(
            user=user,
            status=SubscriptionStatus.ACTIVE,
            end_date__gt=now
        ).order_by('-end_date').first()

        if active_sub:
            start_date = active_sub.end_date
            end_date = active_sub.end_date + timedelta(days=duration_days)
        else:
            start_date = now
            end_date = now + timedelta(days=duration_days)

        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            start_date=start_date,
            end_date=end_date,
            status=SubscriptionStatus.ACTIVE,
            price_paid=price
        )

        formatted_price = f"{price:,.0f}".replace(',', ' ')
        Transaction.objects.create(
            user=user,
            transaction_type=TransactionType.SUBSCRIPTION,
            amount=price,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"-{formatted_price} UZS — Subscription sotib olindi ({plan.name})",
            status=TransactionStatus.SUCCESS,
            reference_id=str(subscription.id),
            metadata={'subscription_id': subscription.id, 'plan_id': plan.id, 'duration_days': duration_days}
        )

        subscription_created_signal.send(
            sender=Subscription,
            subscription=subscription,
            user=user,
            plan=plan
        )

        return subscription

    @staticmethod
    @transaction.atomic
    def activate_promo_code(user, code_text: str) -> PromoCodeActivation:
        """
        Promokodni tekshiradi, ishlatilganlar sonini oshiradi va balansga pul qo'shadi.
        Bitta user bitta promokodni faqat 1 marta ishlata oladi.
        """
        clean_code = code_text.strip().upper()
        if not clean_code:
            raise ValidationError("Promokod kiritilmadi.")

        try:
            promo = PromoCode.objects.select_for_update().get(code__iexact=clean_code)
        except PromoCode.DoesNotExist:
            raise ValidationError("Bunday promokod mavjud emas.")

        if not promo.is_active:
            raise ValidationError("Ushbu promokod faol emas.")

        if promo.activations_count >= promo.activation_limit:
            raise ValidationError("Ushbu promokodning aktivatsiya limiti tugagan.")

        now = timezone.now()
        if promo.valid_from and now < promo.valid_from:
            raise ValidationError("Ushbu promokodning amal qilish muddati hali boshlanmagan.")

        if promo.valid_until and now > promo.valid_until:
            raise ValidationError("Ushbu promokodning amal qilish muddati tugagan.")

        if PromoCodeActivation.objects.filter(promo_code=promo, user=user).exists():
            raise ValidationError("Siz ushbu promokodni allaqachon ishlatgansiz.")

        # Aktivatsiya sonini oshirish
        promo.activations_count += 1
        if promo.activations_count >= promo.activation_limit:
            # Limit tugasa
            promo.is_active = False
        promo.save(update_fields=['activations_count', 'is_active', 'updated_at'])

        # Balansni to'ldirish
        balance = Balance.objects.select_for_update().get_or_create(
            user=user,
            defaults={'amount': Decimal('0.00')}
        )[0]

        balance_before = balance.amount
        balance_after = balance_before + promo.amount

        balance.amount = balance_after
        balance.save(update_fields=['amount', 'updated_at'])

        activation = PromoCodeActivation.objects.create(
            promo_code=promo,
            user=user,
            amount_received=promo.amount
        )

        formatted_amount = f"{promo.amount:,.0f}".replace(',', ' ')
        Transaction.objects.create(
            user=user,
            transaction_type=TransactionType.PROMO_CODE,
            amount=promo.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"+{formatted_amount} UZS — Promo code faollashtirildi ({promo.code})",
            status=TransactionStatus.SUCCESS,
            reference_id=str(activation.id),
            metadata={'promo_code': promo.code, 'activation_id': activation.id}
        )

        promo_code_activated_signal.send(
            sender=PromoCodeActivation,
            activation=activation,
            user=user,
            promo_code=promo,
            amount=promo.amount
        )

        return activation

    @staticmethod
    @transaction.atomic
    def admin_adjust_balance(
        admin_user,
        target_user,
        amount: Decimal,
        reason: str = ""
    ) -> Transaction:
        """
        ADMIN yoki SUPER_ADMIN tomonidan foydalanuvchi balansini qo'lda to'ldirish yoki yechish.
        """
        amount = Decimal(str(amount))
        if amount == Decimal('0.00'):
            raise ValidationError("O‘zgarish summasi 0 bo‘lishi mumkin emas.")

        balance = Balance.objects.select_for_update().get_or_create(
            user=target_user,
            defaults={'amount': Decimal('0.00')}
        )[0]

        balance_before = balance.amount
        balance_after = balance_before + amount

        if balance_after < Decimal('0.00'):
            raise ValidationError("Balans manfiy bo‘lib qolishi mumkin emas.")

        balance.amount = balance_after
        balance.save(update_fields=['amount', 'updated_at'])

        is_credit = amount > Decimal('0.00')
        tx_type = TransactionType.ADMIN_CREDIT if is_credit else TransactionType.ADMIN_DEBIT
        abs_amount = abs(amount)
        formatted_amount = f"{abs_amount:,.0f}".replace(',', ' ')
        sign = "+" if is_credit else "-"

        desc_reason = f": {reason}" if reason else ""
        desc = f"{sign}{formatted_amount} UZS — Admin tuzatishi{desc_reason}"

        tx = Transaction.objects.create(
            user=target_user,
            transaction_type=tx_type,
            amount=abs_amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=desc,
            status=TransactionStatus.SUCCESS,
            metadata={
                'adjusted_by_id': getattr(admin_user, 'id', None),
                'reason': reason
            }
        )
        return tx
