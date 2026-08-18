from datetime import timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

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
)
from apps.billing.services import BillingService
from apps.billing.signals import (
    payment_completed_signal,
    test_purchased_signal,
    subscription_created_signal,
    promo_code_activated_signal,
)

User = get_user_model()


class BillingSystemTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Regular user 1
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        self.balance1, _ = Balance.objects.get_or_create(user=self.user1)

        # Regular user 2
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123'
        )

        # Admin user
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpassword123'
        )

        # Standard subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name="Oylik obuna",
            duration_days=30,
            price=Decimal('50000.00'),
            is_active=True
        )

    # ------------------------------------------------------------------------
    # 1. BALANCE & REGISTRATION BONUS
    # ------------------------------------------------------------------------

    def test_default_balance_creation(self):
        """User yaratilganda default balans 0 UZS bo'ladi."""
        self.assertEqual(self.balance1.amount, Decimal('0.00'))

    def test_registration_bonus_flow(self):
        """SUPER_ADMIN Registration Bonus belgilaganda yangi userga bonus tushishi kerak."""
        BillingSetting.set_registration_bonus(Decimal('10000.00'))

        new_user = User.objects.create_user(
            username='bonus_user',
            email='bonus@example.com',
            password='password123'
        )

        new_balance = Balance.objects.get(user=new_user)
        self.assertEqual(new_balance.amount, Decimal('10000.00'))

        # Tranzaksiya yozilganligini tekshirish
        tx = Transaction.objects.get(user=new_user, transaction_type=TransactionType.REGISTRATION_BONUS)
        self.assertEqual(tx.amount, Decimal('10000.00'))
        self.assertEqual(tx.balance_after, Decimal('10000.00'))
        self.assertIn('+10 000 UZS', tx.description)

    def test_balance_view_api(self):
        """GET /api/v1/balance/ balansi va statistikani qaytaradi."""
        self.balance1.amount = Decimal('25000.00')
        self.balance1.save()

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(reverse('billing:balance'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['amount'])), Decimal('25000.00'))
        self.assertFalse(response.data['has_active_subscription'])

    def test_transaction_history_api(self):
        """GET /api/v1/balance/history/ tranzaksiyalar tarixini qaytaradi."""
        Transaction.objects.create(
            user=self.user1,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('50000.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50000.00'),
            description="+50 000 UZS — Balance to‘ldirildi"
        )

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(reverse('billing:balance-history'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Results can be a list or paginated dict
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['transaction_type'], TransactionType.DEPOSIT)

    # ------------------------------------------------------------------------
    # 2. PAYMENTS & GATEWAYS (CLICK, PAYME, TRANSFER)
    # ------------------------------------------------------------------------

    def test_create_payment_api(self):
        """POST /api/v1/payments/ to'lov yaratadi."""
        self.client.force_authenticate(user=self.user1)
        payload = {
            'amount': '50000.00',
            'payment_method': PaymentMethod.CLICK
        }
        response = self.client.post(reverse('billing:payments'), data=payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['payment_method'], PaymentMethod.CLICK)
        self.assertEqual(response.data['status'], PaymentStatus.PENDING)
        self.assertIn('checkout_url', response.data)

    def test_click_webhook_prepare_and_complete(self):
        """Click Prepare va Complete webhooklarini sinash."""
        payment = BillingService.create_payment(
            user=self.user1,
            amount=Decimal('30000.00'),
            payment_method=PaymentMethod.CLICK
        )

        # 1. Prepare
        prepare_payload = {
            'action': 0,
            'click_trans_id': 123456,
            'merchant_trans_id': str(payment.id),
            'amount': 30000.0,
            'error': 0
        }
        resp_prepare = self.client.post(reverse('billing:payment-webhook-click'), data=prepare_payload)
        self.assertEqual(resp_prepare.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_prepare.data['error'], 0)

        # 2. Complete
        complete_payload = {
            'action': 1,
            'click_trans_id': 123456,
            'merchant_trans_id': str(payment.id),
            'amount': 30000.0,
            'error': 0
        }
        resp_complete = self.client.post(reverse('billing:payment-webhook-click'), data=complete_payload)
        self.assertEqual(resp_complete.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_complete.data['error'], 0)

        # Balans tekshirish
        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('30000.00'))

        # Tranzaksiya tekshirish
        tx = Transaction.objects.filter(user=self.user1, transaction_type=TransactionType.DEPOSIT).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('30000.00'))

    def test_payme_webhook_perform(self):
        """Payme JSON-RPC webhookini sinash."""
        payment = BillingService.create_payment(
            user=self.user1,
            amount=Decimal('40000.00'),
            payment_method=PaymentMethod.PAYME
        )

        payload = {
            'id': 101,
            'method': 'PerformTransaction',
            'params': {
                'id': 'payme_trans_123',
                'account': {'order_id': str(payment.id)}
            }
        }
        response = self.client.post(
            reverse('billing:payment-webhook-payme'),
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result']['state'], 2)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('40000.00'))

    def test_transfer_admin_approval(self):
        """Bank o'tkazmasi (TRANSFER) to'lovini admin tomonidan tasdiqlash."""
        payment = BillingService.create_payment(
            user=self.user1,
            amount=Decimal('70000.00'),
            payment_method=PaymentMethod.TRANSFER
        )

        # Admin approve
        self.client.force_authenticate(user=self.admin_user)
        approve_url = reverse('billing:admin-payment-approve', kwargs={'pk': payment.id})
        response = self.client.post(approve_url, data={'admin_notes': 'Bank orqali qabul qilindi'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('70000.00'))

    # ------------------------------------------------------------------------
    # 3. PROMO CODES
    # ------------------------------------------------------------------------

    def test_promo_code_activation_and_limits(self):
        """Promokod yaratish, aktivatsiya qilish, limit va bir martalik foydalanish."""
        promo = PromoCode.objects.create(
            code='PROTESTY100',
            amount=Decimal('100000.00'),
            activation_limit=2,
            is_active=True
        )

        # 1. User 1 aktivatsiya qiladi
        self.client.force_authenticate(user=self.user1)
        resp1 = self.client.post(reverse('billing:promo-code-activate'), data={'code': 'protesty100'})
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('100000.00'))

        # 2. User 1 ikkinchi marta ishlata olmaydi
        resp1_dup = self.client.post(reverse('billing:promo-code-activate'), data={'code': 'PROTESTY100'})
        self.assertEqual(resp1_dup.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. User 2 aktivatsiya qiladi (2-chi va oxirgi limit)
        self.client.force_authenticate(user=self.user2)
        resp2 = self.client.post(reverse('billing:promo-code-activate'), data={'code': 'PROTESTY100'})
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        # 4. User 3 (yoki boshqa user) limit tugagani sababli ishlata olmaydi
        user3 = User.objects.create_user(username='user3', password='password123')
        self.client.force_authenticate(user=user3)
        resp3 = self.client.post(reverse('billing:promo-code-activate'), data={'code': 'PROTESTY100'})
        self.assertEqual(resp3.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------------
    # 4. TEST PURCHASES
    # ------------------------------------------------------------------------

    def test_test_purchase_flow(self):
        """Test sotib olish, yetarli mablag' tekshiruvi, balans yechilishi va takroriy xarid bloklanishi."""
        self.balance1.amount = Decimal('15000.00')
        self.balance1.save()

        self.client.force_authenticate(user=self.user1)

        # 1. 10 000 UZS li test 1 ni sotib olish
        buy_resp = self.client.post(reverse('billing:purchases'), data={'test_id': 1, 'price': '10000.00'})
        self.assertEqual(buy_resp.status_code, status.HTTP_201_CREATED)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('5000.00'))

        # Tranzaksiya yozilganligini tekshirish
        tx = Transaction.objects.get(user=self.user1, transaction_type=TransactionType.TEST_PURCHASE)
        self.assertEqual(tx.amount, Decimal('10000.00'))
        self.assertEqual(tx.balance_after, Decimal('5000.00'))

        # 2. Xarid qilinganligini tekshirish API
        check_url = f"{reverse('billing:purchase-check')}?test_id=1"
        check_resp = self.client.get(check_url)
        self.assertEqual(check_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(check_resp.data['has_access'])
        self.assertEqual(check_resp.data['access_type'], 'PURCHASE')

        # 3. Qayta sotib olishga urinish (bloklanadi)
        dup_resp = self.client.post(reverse('billing:purchases'), data={'test_id': 1, 'price': '10000.00'})
        self.assertEqual(dup_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Mablag' yetarli bo'lmaganda (balans 5 000 UZS, narx 10 000 UZS)
        insufficient_resp = self.client.post(reverse('billing:purchases'), data={'test_id': 2, 'price': '10000.00'})
        self.assertEqual(insufficient_resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------------
    # 5. SUBSCRIPTIONS
    # ------------------------------------------------------------------------

    def test_subscription_purchase_and_extension(self):
        """Oylik obuna sotib olish, muddatini tekshirish va qayta sotib olganda muddat uzaytirilishi."""
        self.balance1.amount = Decimal('120000.00')
        self.balance1.save()

        self.client.force_authenticate(user=self.user1)

        # 1. Birinchi obuna xaridi (50 000 UZS)
        sub_resp = self.client.post(reverse('billing:subscription-purchase'), data={'plan_id': self.plan.id})
        self.assertEqual(sub_resp.status_code, status.HTTP_201_CREATED)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('70000.00'))

        sub1 = Subscription.objects.filter(user=self.user1, status=SubscriptionStatus.ACTIVE).first()
        self.assertIsNotNone(sub1)
        self.assertTrue(sub1.is_active_now)

        # Obunasi bor user uchun har qanday test ochiladi
        check_url = f"{reverse('billing:purchase-check')}?test_id=999"
        check_resp = self.client.get(check_url)
        self.assertEqual(check_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(check_resp.data['has_access'])
        self.assertEqual(check_resp.data['access_type'], 'SUBSCRIPTION')

        # 2. Obunani uzaytirish (ikkinchi marta sotib olish)
        first_end_date = sub1.end_date
        sub_resp2 = self.client.post(reverse('billing:subscription-purchase'), data={'plan_id': self.plan.id})
        self.assertEqual(sub_resp2.status_code, status.HTTP_201_CREATED)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('20000.00'))

        sub2 = Subscription.objects.filter(user=self.user1).order_by('-end_date').first()
        self.assertAlmostEqual(
            (sub2.end_date - first_end_date).total_seconds(),
            timedelta(days=30).total_seconds(),
            delta=60
        )

    # ------------------------------------------------------------------------
    # 6. ADMIN MANAGEMENT & SETTINGS
    # ------------------------------------------------------------------------

    def test_admin_balance_adjust_api(self):
        """Admin foydalanuvchi balansiga to'g'ridan-to'g'ri pul qo'shadi yoki yechadi."""
        self.client.force_authenticate(user=self.admin_user)

        adjust_url = reverse('billing:admin-balance-adjust')
        payload = {
            'user_id': self.user1.id,
            'amount': '35000.00',
            'reason': 'Veb-aktsiya g‘olibi'
        }
        response = self.client.post(adjust_url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.amount, Decimal('35000.00'))

        tx = Transaction.objects.get(user=self.user1, transaction_type=TransactionType.ADMIN_CREDIT)
        self.assertEqual(tx.amount, Decimal('35000.00'))
        self.assertIn('Veb-aktsiya g‘olibi', tx.description)

    def test_admin_billing_settings_api(self):
        """SUPER_ADMIN billing parametrlarini (bonus, subscription narxi) o'zgartiradi."""
        self.client.force_authenticate(user=self.admin_user)

        settings_url = reverse('billing:admin-billing-settings')
        payload = {
            'registration_bonus': '15000.00',
            'default_subscription_price': '60000.00'
        }
        put_resp = self.client.put(settings_url, data=payload)
        self.assertEqual(put_resp.status_code, status.HTTP_200_OK)

        self.assertEqual(BillingSetting.get_registration_bonus(), Decimal('15000.00'))

    def test_non_admin_forbidden_from_admin_endpoints(self):
        """Oddiy foydalanuvchi admin endpointlariga kira olmaydi (403 Forbidden)."""
        self.client.force_authenticate(user=self.user1)

        adjust_url = reverse('billing:admin-balance-adjust')
        response = self.client.post(adjust_url, data={'user_id': self.user2.id, 'amount': '1000.00'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------------------------------
    # 7. CROSS-DEVELOPER SIGNALS (DEV 4)
    # ------------------------------------------------------------------------

    def test_signals_fire_correctly(self):
        """To'lov, test xaridi va promokod signallari to'g'ri chaqirilishini tekshirish."""
        signal_data = {}

        def payment_handler(sender, **kwargs):
            signal_data['payment_received'] = kwargs

        def test_purchase_handler(sender, **kwargs):
            signal_data['test_purchased'] = kwargs

        payment_completed_signal.connect(payment_handler)
        test_purchased_signal.connect(test_purchase_handler)

        try:
            # 1. To'lov yakunlanishi signali
            payment = BillingService.create_payment(self.user1, Decimal('10000.00'), PaymentMethod.CLICK)
            BillingService.complete_payment(payment.id)
            self.assertIn('payment_received', signal_data)
            self.assertEqual(signal_data['payment_received']['amount'], Decimal('10000.00'))

            # 2. Test xaridi signali
            BillingService.purchase_test(self.user1, test_id=88, override_price=Decimal('5000.00'))
            self.assertIn('test_purchased', signal_data)
            self.assertEqual(signal_data['test_purchased']['test_id'], 88)
        finally:
            payment_completed_signal.disconnect(payment_handler)
            test_purchased_signal.disconnect(test_purchase_handler)
