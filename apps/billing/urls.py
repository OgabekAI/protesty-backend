from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.billing.views import (
    AdminBalanceAdjustView,
    AdminBalanceListView,
    AdminBillingSettingView,
    AdminPaymentApproveView,
    AdminPaymentListView,
    AdminPaymentRejectView,
    AdminPromoCodeViewSet,
    AdminTransactionListView,
    BalanceView,
    ClickWebhookView,
    PaymeWebhookView,
    PaymentCreateView,
    PaymentDetailView,
    PaymentListCreateView,
    PaymentListView,
    PromoCodeActivateView,
    PurchaseCheckView,
    PurchaseListCreateView,
    PurchaseListView,
    PurchaseTestView,
    SubscriptionMyView,
    SubscriptionPlanListView,
    SubscriptionPurchaseView,
    TransactionHistoryView,
    TransferProofUploadView,
)

app_name = 'billing'

router = DefaultRouter()
router.register(r'admin/promo-codes', AdminPromoCodeViewSet, basename='admin-promo-codes')

urlpatterns = [
    # 1. Balance & Transactions
    path('balance/', BalanceView.as_view(), name='balance'),
    path('balance/history/', TransactionHistoryView.as_view(), name='balance-history'),
    path('balance/transactions/', TransactionHistoryView.as_view(), name='balance-transactions'),

    # 2. Payments
    path('payments/', PaymentListCreateView.as_view(), name='payments'),
    path('payments/create/', PaymentCreateView.as_view(), name='payment-create'),
    path('payments/<uuid:pk>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('payments/<uuid:pk>/proof/', TransferProofUploadView.as_view(), name='payment-proof'),
    path('payments/webhook/click/', ClickWebhookView.as_view(), name='payment-webhook-click'),
    path('payments/webhook/payme/', PaymeWebhookView.as_view(), name='payment-webhook-payme'),

    # 3. Purchases (Test Purchase)
    path('purchases/', PurchaseListCreateView.as_view(), name='purchases'),
    path('purchases/create/', PurchaseTestView.as_view(), name='purchase-create'),
    path('purchases/buy/', PurchaseTestView.as_view(), name='purchase-buy'),
    path('purchases/check/', PurchaseCheckView.as_view(), name='purchase-check'),

    # 4. Subscriptions
    path('subscriptions/plans/', SubscriptionPlanListView.as_view(), name='subscription-plans'),
    path('subscriptions/my/', SubscriptionMyView.as_view(), name='subscription-my'),
    path('subscriptions/purchase/', SubscriptionPurchaseView.as_view(), name='subscription-purchase'),

    # 5. Promo Codes
    path('promo-codes/activate/', PromoCodeActivateView.as_view(), name='promo-code-activate'),

    # 6. Admin & Super Admin Management
    path('admin/payments/', AdminPaymentListView.as_view(), name='admin-payments'),
    path('admin/payments/<uuid:pk>/approve/', AdminPaymentApproveView.as_view(), name='admin-payment-approve'),
    path('admin/payments/<uuid:pk>/reject/', AdminPaymentRejectView.as_view(), name='admin-payment-reject'),
    path('admin/balances/', AdminBalanceListView.as_view(), name='admin-balances'),
    path('admin/balances/adjust/', AdminBalanceAdjustView.as_view(), name='admin-balance-adjust'),
    path('admin/transactions/', AdminTransactionListView.as_view(), name='admin-transactions'),
    path('admin/billing/settings/', AdminBillingSettingView.as_view(), name='admin-billing-settings'),

    # Router URLs for admin ViewSets
    path('', include(router.urls)),
]
