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
        "webhooks/payments/<str:provider>",
        views.PaymentWebhookView.as_view(),
        name="payment-webhook",
    ),
]
