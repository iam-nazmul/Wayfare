from django.urls import path

from . import views

urlpatterns = [
    path(
        "bookings/<str:pnr>/payment-intents",
        views.PaymentIntentCreateView.as_view(),
        name="payment-intent-create",
    ),
    path(
        "bookings/<str:pnr>/payment-intents/<uuid:intent_id>",
        views.PaymentIntentDetailView.as_view(),
        name="payment-intent-detail",
    ),
    path(
        "bookings/<str:pnr>/payment-intents/<uuid:intent_id>/confirm",
        views.SandboxConfirmView.as_view(),
        name="payment-intent-confirm",
    ),
    path("bookings/<str:pnr>/payments", views.PaymentListView.as_view(), name="payment-list"),
    path(
        "bookings/<str:pnr>/refunds",
        views.BookingRefundListView.as_view(),
        name="booking-refund-list",
    ),
    path("ops/refunds", views.OpsRefundQueueView.as_view(), name="ops-refund-queue"),
    path(
        "ops/refunds/<uuid:refund_id>/approve",
        views.OpsRefundApproveView.as_view(),
        name="ops-refund-approve",
    ),
    path(
        "ops/refunds/<uuid:refund_id>/reject",
        views.OpsRefundRejectView.as_view(),
        name="ops-refund-reject",
    ),
    path(
        "webhooks/payments/<str:provider>",
        views.PaymentWebhookView.as_view(),
        name="payment-webhook",
    ),
]
