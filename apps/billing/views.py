from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

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
from apps.billing.permissions import IsAdminOrSuperAdmin, IsSuperAdmin
from apps.billing.serializers import (
    AdminBalanceAdjustSerializer,
    BalanceSerializer,
    BillingSettingSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    PromoCodeActivateSerializer,
    PromoCodeAdminSerializer,
    PurchaseCheckSerializer,
    PurchaseCreateSerializer,
    PurchaseSerializer,
    SubscriptionPlanSerializer,
    SubscriptionPurchaseSerializer,
    SubscriptionSerializer,
    TransactionSerializer,
    TransferProofSerializer,
)
from apps.billing.services import BillingService

User = get_user_model()


def resolve_request_user(request):
    """
    Foydalanuvchini autentifikatsiya yoki test parametrlaridan aniqlaydi.
    """
    if request.user and request.user.is_authenticated:
        return request.user

    user_id = request.query_params.get('user_id') if hasattr(request, 'query_params') else None
    if not user_id and isinstance(request.data, dict):
        user_id = request.data.get('user_id')

    if user_id and str(user_id).isdigit():
        user, _ = User.objects.get_or_create(id=int(user_id), defaults={'username': f"user_{user_id}"})
        return user

    # Default test fallback if exists
    user = User.objects.first()
    if not user:
        user = User.objects.create_user(username='demo_user', password='password123')
    return user


# ============================================================================
# 1. USER BALANCE & TRANSACTIONS
# ============================================================================

class BalanceView(APIView):
    """
    GET /api/v1/balance/
    Foydalanuvchi hisob balansi, jami kiritilgan va sarflangan pullar statistikasi.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        user = resolve_request_user(request)
        balance = BillingService.get_or_create_balance(user)


        # Statistika
        total_deposited = Transaction.objects.filter(
            user=user,
            transaction_type__in=[
                TransactionType.DEPOSIT,
                TransactionType.REGISTRATION_BONUS,
                TransactionType.PROMO_CODE,
                TransactionType.ADMIN_CREDIT
            ]
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        total_spent = Transaction.objects.filter(
            user=user,
            transaction_type__in=[
                TransactionType.TEST_PURCHASE,
                TransactionType.SUBSCRIPTION,
                TransactionType.ADMIN_DEBIT
            ]
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        data = BalanceSerializer(balance).data
        data['total_deposited'] = total_deposited
        data['total_spent'] = total_spent

        return Response(data, status=status.HTTP_200_OK)


class TransactionHistoryView(generics.ListAPIView):
    """
    GET /api/v1/balance/history/
    GET /api/v1/balance/transactions/
    Foydalanuvchining barcha balans o'zgarishlari tarixi (filtr va pagination bilan).
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = resolve_request_user(self.request)
        qs = Transaction.objects.filter(user=user)
        tx_type = self.request.query_params.get('type')
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)
        return qs.order_by('-created_at')


# ============================================================================
# 2. PAYMENTS (CLICK, PAYME, TRANSFER)
# ============================================================================

class PaymentListCreateView(APIView):
    """
    GET /api/v1/payments/ - Foydalanuvchining to'lovlari tarixi
    POST /api/v1/payments/ - Yangi to'lov yaratish (Click, Payme, Transfer)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        user = resolve_request_user(request)
        payments = Payment.objects.filter(user=user).order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount']
        payment_method = serializer.validated_data['payment_method']
        metadata = serializer.validated_data.get('metadata', {})
        user = resolve_request_user(request)

        try:
            payment = BillingService.create_payment(
                user=user,
                amount=amount,
                payment_method=payment_method,
                metadata=metadata
            )
            return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'detail': str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)



# For backwards compatibility / explicit URLs
PaymentCreateView = PaymentListCreateView
PaymentListView = PaymentListCreateView



class PaymentDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/payments/<uuid:pk>/
    To'lov holati va tafsilotlari.
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self.request.user, 'role', None) in ['ADMIN', 'SUPER_ADMIN'] or self.request.user.is_staff:
            return Payment.objects.all()
        return Payment.objects.filter(user=self.request.user)


class TransferProofUploadView(APIView):
    """
    POST /api/v1/payments/<uuid:pk>/proof/
    Transfer usulida to'lov qilinganida bank cheki rasmini yuklash.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk, user=request.user, payment_method=PaymentMethod.TRANSFER)
        except Payment.DoesNotExist:
            return Response({'detail': 'To‘lov topilmadi yoki usuli TRANSFER emas.'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == PaymentStatus.COMPLETED:
            return Response({'detail': 'Ushbu to‘lov allaqachon tasdiqlangan.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TransferProofSerializer(payment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Chek muvaffaqiyatli yuklandi. Admin tekshiruvidan so‘ng balans to‘ldiriladi.',
            'payment': PaymentSerializer(payment).data
        }, status=status.HTTP_200_OK)


# ============================================================================
# 3. PAYMENT GATEWAY WEBHOOKS (CLICK & PAYME)
# ============================================================================

class ClickWebhookView(APIView):
    """
    POST /api/v1/payments/webhook/click/
    Click tizimidan Prepare va Complete so'rovlarini qabul qilish.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        action = request.data.get('action')
        click_trans_id = request.data.get('click_trans_id')
        merchant_trans_id = request.data.get('merchant_trans_id')
        amount = request.data.get('amount')
        error = request.data.get('error', 0)

        if str(error) != "0":
            return Response({'error': -1, 'error_note': 'Click xatosi'}, status=status.HTTP_200_OK)

        try:
            payment = Payment.objects.get(id=merchant_trans_id)
        except (Payment.DoesNotExist, ValueError):
            return Response({'error': -5, 'error_note': 'Buyurtma topilmadi'}, status=status.HTTP_200_OK)

        # Action: 0 - Prepare, 1 - Complete
        if str(action) == "0":
            return Response({
                'click_trans_id': click_trans_id,
                'merchant_trans_id': merchant_trans_id,
                'merchant_prepare_id': str(payment.id),
                'error': 0,
                'error_note': 'Success'
            }, status=status.HTTP_200_OK)
        elif str(action) == "1":
            try:
                BillingService.complete_payment(
                    payment_id=payment.id,
                    provider_transaction_id=str(click_trans_id),
                    metadata={'click_raw': request.data}
                )
                return Response({
                    'click_trans_id': click_trans_id,
                    'merchant_trans_id': merchant_trans_id,
                    'merchant_confirm_id': str(payment.id),
                    'error': 0,
                    'error_note': 'Success'
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({'error': -8, 'error_note': str(e)}, status=status.HTTP_200_OK)

        return Response({'error': -3, 'error_note': 'Noma’lum amal'}, status=status.HTTP_200_OK)


class PaymeWebhookView(APIView):
    """
    POST /api/v1/payments/webhook/payme/
    Payme JSON-RPC merchant so'rovlarini qabul qilish.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        rpc_method = data.get('method')
        params = data.get('params', {})
        rpc_id = data.get('id')

        account = params.get('account', {})
        order_id = account.get('order_id') or params.get('order_id')

        if rpc_method == "CheckPerformTransaction":
            if not order_id or not Payment.objects.filter(id=order_id).exists():
                return Response({'id': rpc_id, 'error': {'code': -31050, 'message': {'uz': 'Buyurtma topilmadi'}}}, status=status.HTTP_200_OK)
            return Response({'id': rpc_id, 'result': {'allow': True}}, status=status.HTTP_200_OK)

        elif rpc_method in ["PerformTransaction", "CreateTransaction"]:
            if not order_id:
                return Response({'id': rpc_id, 'error': {'code': -31050, 'message': {'uz': 'Buyurtma topilmadi'}}}, status=status.HTTP_200_OK)
            try:
                payment = BillingService.complete_payment(
                    payment_id=order_id,
                    provider_transaction_id=str(params.get('id', '')),
                    metadata={'payme_raw': params}
                )
                return Response({
                    'id': rpc_id,
                    'result': {
                        'transaction': str(payment.id),
                        'perform_time': int(payment.completed_at.timestamp() * 1000) if payment.completed_at else 0,
                        'state': 2
                    }
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({'id': rpc_id, 'error': {'code': -31008, 'message': {'uz': str(e)}}}, status=status.HTTP_200_OK)

        elif rpc_method == "CheckTransaction":
            return Response({
                'id': rpc_id,
                'result': {
                    'state': 2,
                    'reason': None
                }
            }, status=status.HTTP_200_OK)

        return Response({'id': rpc_id, 'result': {'status': 'ok'}}, status=status.HTTP_200_OK)


# ============================================================================
# 4. PURCHASES (TEST SOTIB OLISH)
# ============================================================================

class PurchaseListCreateView(APIView):
    """
    GET /api/v1/purchases/ - Foydalanuvchi sotib olgan testlar ro'yxati
    POST /api/v1/purchases/ - Foydalanuvchi alohida testni balansi orqali sotib oladi
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        user = resolve_request_user(request)
        purchases = Purchase.objects.filter(user=user).order_by('-created_at')
        serializer = PurchaseSerializer(purchases, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PurchaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        test_id = serializer.validated_data['test_id']
        price = serializer.validated_data.get('price')
        user = resolve_request_user(request)

        try:
            purchase = BillingService.purchase_test(
                user=user,
                test_id=test_id,
                override_price=price
            )
            return Response({
                'message': 'Test muvaffaqiyatli sotib olindi.',
                'purchase': PurchaseSerializer(purchase).data
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'detail': str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)


# For backwards compatibility / explicit URLs
PurchaseTestView = PurchaseListCreateView
PurchaseListView = PurchaseListCreateView



class PurchaseCheckView(APIView):
    """
    GET /api/v1/purchases/check/?test_id=123
    DEV 2 yoki frontend uchun test sotib olinganligi yoki oylik obuna orqali ochiqligini tekshirish.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        test_id_str = request.query_params.get('test_id')
        if not test_id_str or not test_id_str.isdigit():
            return Response({'detail': 'test_id parametri talab qilinadi.'}, status=status.HTTP_400_BAD_REQUEST)

        test_id = int(test_id_str)
        user = resolve_request_user(request)
        has_purchased = Purchase.objects.filter(user=user, test_id=test_id).exists()
        has_subscription = Subscription.objects.filter(
            user=user,
            status=SubscriptionStatus.ACTIVE,
            end_date__gt=timezone.now()
        ).exists()

        has_access = has_purchased or has_subscription
        access_type = "PURCHASE" if has_purchased else ("SUBSCRIPTION" if has_subscription else "NONE")

        return Response({
            'test_id': test_id,
            'has_access': has_access,
            'access_type': access_type,
            'has_purchased_directly': has_purchased,
            'has_active_subscription': has_subscription
        }, status=status.HTTP_200_OK)


# ============================================================================
# 5. SUBSCRIPTIONS (OBUNA)
# ============================================================================

class SubscriptionPlanListView(generics.ListAPIView):
    """
    GET /api/v1/subscriptions/plans/
    Mavjud faol obuna rejalari ro'yxati.
    """
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        if not SubscriptionPlan.objects.exists():
            SubscriptionPlan.objects.create(
                name="Oylik obuna",
                duration_days=30,
                price=Decimal('50000.00'),
                is_active=True,
                description="Barcha testlarga 1 oy davomida to‘liq cheksiz kirish."
            )
        return SubscriptionPlan.objects.filter(is_active=True).order_by('price')


class SubscriptionMyView(APIView):
    """
    GET /api/v1/subscriptions/my/
    Foydalanuvchining joriy faol obunasi va obunalar tarixi.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        user = resolve_request_user(request)
        now = timezone.now()
        active_sub = Subscription.objects.filter(
            user=user,
            status=SubscriptionStatus.ACTIVE,
            end_date__gt=now
        ).order_by('-end_date').first()

        all_subs = Subscription.objects.filter(user=user).order_by('-created_at')

        return Response({
            'is_active': bool(active_sub),
            'active_subscription': SubscriptionSerializer(active_sub).data if active_sub else None,
            'history': SubscriptionSerializer(all_subs, many=True).data
        }, status=status.HTTP_200_OK)


class SubscriptionPurchaseView(APIView):
    """
    POST /api/v1/subscriptions/purchase/
    Foydalanuvchi balans orqali obuna sotib oladi yoki amaldagi obunasini uzaytiradi.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SubscriptionPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan_id = serializer.validated_data.get('plan_id')
        user = resolve_request_user(request)

        try:
            subscription = BillingService.purchase_subscription(
                user=user,
                plan_id=plan_id
            )
            return Response({
                'message': 'Obuna muvaffaqiyatli faollashtirildi.',
                'subscription': SubscriptionSerializer(subscription).data
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'detail': str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)


# ============================================================================
# 6. PROMO CODES
# ============================================================================

class PromoCodeActivateView(APIView):
    """
    POST /api/v1/promo-codes/activate/
    Foydalanuvchi promokodni kiritib balansini to'ldiradi.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PromoCodeActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']
        user = resolve_request_user(request)

        try:
            activation = BillingService.activate_promo_code(
                user=user,
                code_text=code
            )
            formatted_amount = f"{activation.amount_received:,.0f}".replace(',', ' ')
            return Response({
                'message': f"Promokod muvaffaqiyatli ishlatildi! Balansingizga +{formatted_amount} UZS qo‘shildi.",
                'amount_added': activation.amount_received,
                'activated_at': activation.activated_at.isoformat()
            }, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'detail': str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)



# ============================================================================
# 7. ADMIN / SUPER_ADMIN MANAGEMENT ENDPOINTS
# ============================================================================

class AdminPromoCodeViewSet(viewsets.ModelViewSet):
    """
    CRUD /api/v1/admin/promo-codes/
    Admin va Super Admin uchun promokodlarni yaratish va boshqarish.
    """
    queryset = PromoCode.objects.all().order_by('-created_at')
    serializer_class = PromoCodeAdminSerializer
    permission_classes = [IsAdminOrSuperAdmin]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminPaymentListView(generics.ListAPIView):
    """
    GET /api/v1/admin/payments/
    Tizimdagi barcha to'lovlar ro'yxati (status, usul va sana bo'yicha filtrlanadi).
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminOrSuperAdmin]

    def get_queryset(self):
        qs = Payment.objects.all().order_by('-created_at')
        status_param = self.request.query_params.get('status')
        method_param = self.request.query_params.get('method')
        user_id = self.request.query_params.get('user_id')

        if status_param:
            qs = qs.filter(status=status_param)
        if method_param:
            qs = qs.filter(payment_method=method_param)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs


class AdminPaymentApproveView(APIView):
    """
    POST /api/v1/admin/payments/<uuid:pk>/approve/
    Admin tomonidan bank o'tkazmasi (TRANSFER) to'lovini tasdiqlash va balansga pul o'tkazish.
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response({'detail': 'To‘lov topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == PaymentStatus.COMPLETED:
            return Response({'detail': 'Ushbu to‘lov allaqachon tasdiqlangan.'}, status=status.HTTP_400_BAD_REQUEST)

        admin_notes = request.data.get('admin_notes', 'Admin tomonidan tasdiqlandi')
        try:
            completed_payment = BillingService.complete_payment(
                payment_id=payment.id,
                admin_notes=admin_notes,
                metadata={'approved_by_id': getattr(request.user, 'id', None)}
            )
            return Response({
                'message': 'To‘lov muvaffaqiyatli tasdiqlandi va balans to‘ldirildi.',
                'payment': PaymentSerializer(completed_payment).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminPaymentRejectView(APIView):
    """
    POST /api/v1/admin/payments/<uuid:pk>/reject/
    Admin tomonidan to'lovni rad etish.
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response({'detail': 'To‘lov topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        reason = request.data.get('reason', 'Admin tomonidan rad etildi')
        try:
            payment = BillingService.fail_or_cancel_payment(
                payment_id=payment.id,
                status=PaymentStatus.CANCELLED,
                admin_notes=reason
            )
            return Response({
                'message': 'To‘lov bekor qilindi.',
                'payment': PaymentSerializer(payment).data
            }, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'detail': str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminBalanceListView(generics.ListAPIView):
    """
    GET /api/v1/admin/balances/
    Barcha foydalanuvchilarning hisob balansi.
    """
    serializer_class = BalanceSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    queryset = Balance.objects.all().order_by('-updated_at')


class AdminBalanceAdjustView(APIView):
    """
    POST /api/v1/admin/balances/adjust/
    Admin tomonidan foydalanuvchi balansiga to'g'ridan-to'g'ri pul qo'shish yoki yechish.
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request):
        serializer = AdminBalanceAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['user_id']
        amount = serializer.validated_data['amount']
        reason = serializer.validated_data.get('reason', '')

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'Foydalanuvchi topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            tx = BillingService.admin_adjust_balance(
                admin_user=request.user,
                target_user=target_user,
                amount=amount,
                reason=reason
            )
            return Response({
                'message': 'Foydalanuvchi balansi muvaffaqiyatli o‘zgartirildi.',
                'transaction': TransactionSerializer(tx).data
            }, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'detail': str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminTransactionListView(generics.ListAPIView):
    """
    GET /api/v1/admin/transactions/
    Tizimdagi barcha audit tranzaksiyalari ro'yxati.
    """
    serializer_class = TransactionSerializer
    permission_classes = [IsAdminOrSuperAdmin]

    def get_queryset(self):
        qs = Transaction.objects.all().order_by('-created_at')
        user_id = self.request.query_params.get('user_id')
        tx_type = self.request.query_params.get('type')
        if user_id:
            qs = qs.filter(user_id=user_id)
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)
        return qs


class AdminBillingSettingView(APIView):
    """
    GET /api/v1/admin/billing/settings/
    PUT /api/v1/admin/billing/settings/
    SUPER_ADMIN: Registratsiya bonusi va standart obuna narxini sozlash.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        bonus = BillingSetting.get_registration_bonus()
        default_sub_plan = SubscriptionPlan.objects.filter(is_active=True).first()
        sub_price = default_sub_plan.price if default_sub_plan else Decimal('50000.00')

        return Response({
            'registration_bonus': bonus,
            'default_subscription_price': sub_price
        }, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = BillingSettingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bonus = serializer.validated_data['registration_bonus']
        sub_price = serializer.validated_data.get('default_subscription_price')

        BillingSetting.set_registration_bonus(bonus)

        if sub_price is not None:
            plan = SubscriptionPlan.objects.filter(is_active=True).first()
            if plan:
                plan.price = sub_price
                plan.save(update_fields=['price', 'updated_at'])
            else:
                SubscriptionPlan.objects.create(
                    name="Oylik obuna",
                    duration_days=30,
                    price=sub_price,
                    is_active=True
                )

        return Response({
            'message': 'Billing sozlamalari muvaffaqiyatli saqlandi.',
            'registration_bonus': bonus,
            'default_subscription_price': sub_price
        }, status=status.HTTP_200_OK)
