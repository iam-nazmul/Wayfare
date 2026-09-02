from django.db import models

from apps.common.models import PublicIdModel, TimestampedModel

from .constants import (
    CaptureMethod,
    IntentStatus,
    LedgerEntryType,
    PaymentStatus,
    RefundStatus,
    ThreeDsStatus,
)


class PaymentIntent(PublicIdModel, TimestampedModel):
    """The provider-side object the SPA confirms against.

    Wayfare never sees the card: the client posts it straight to the provider with the
    ``client_secret``, and we learn the outcome from the webhook.
    """

    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.CASCADE, related_name="payment_intents"
    )
    provider = models.CharField(max_length=32)
    provider_intent_id = models.CharField(max_length=128, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=20, choices=IntentStatus.choices, default=IntentStatus.REQUIRES_PAYMENT
    )
    client_secret = models.CharField(max_length=128)
    capture_method = models.CharField(
        max_length=10, choices=CaptureMethod.choices, default=CaptureMethod.AUTOMATIC
    )
    three_ds_status = models.CharField(
        max_length=16, choices=ThreeDsStatus.choices, default=ThreeDsStatus.NOT_REQUIRED
    )
    idempotency_key = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["booking", "-created_at"], name="idx_intent_booking"),
            models.Index(fields=["status", "created_at"], name="idx_intent_pending"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider_intent_id} {self.status}"


class Payment(PublicIdModel, TimestampedModel):
    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.PROTECT, related_name="payments"
    )
    intent = models.ForeignKey(
        PaymentIntent, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    method = models.CharField(max_length=20, default="CARD")
    provider = models.CharField(max_length=32)
    provider_charge_id = models.CharField(max_length=128, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices)
    #: Brand and last four only — never a PAN, never a CVV (CLAUDE.md invariant 9).
    card_brand = models.CharField(max_length=20, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    authorised_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["booking", "-created_at"], name="idx_payment_booking")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider_charge_id} {self.amount} {self.currency}"


class Refund(PublicIdModel, TimestampedModel):
    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.PROTECT, related_name="refunds"
    )
    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="refunds", null=True, blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=12, choices=RefundStatus.choices, default=RefundStatus.REQUESTED
    )
    reason = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="refunds_requested",
    )
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="refunds_approved",
    )
    provider_refund_id = models.CharField(max_length=128, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    penalty_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refundable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        indexes = [models.Index(fields=["status", "-created_at"], name="idx_refund_queue")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"refund {self.amount} {self.currency} ({self.status})"


class LedgerEntry(TimestampedModel):
    """Append-only money movement. Rows are never updated or deleted."""

    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.PROTECT, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=12, choices=LedgerEntryType.choices)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=128, blank=True)

    class Meta:
        indexes = [models.Index(fields=["booking", "created_at"], name="idx_ledger_booking")]
        ordering = ["created_at"]
        verbose_name_plural = "ledger entries"

    def __str__(self) -> str:
        return f"{self.entry_type} {self.debit or self.credit} {self.currency}"


class ProviderWebhookEvent(TimestampedModel):
    """Every callback the provider sends, exactly once.

    ``provider_event_id`` is unique, so a replayed delivery hits the constraint instead of
    paying for the same booking twice. Webhooks arrive out of order and more than once.
    """

    provider = models.CharField(max_length=32)
    provider_event_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    signature_verified = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["processed_at"],
                name="idx_webhook_pending",
                condition=models.Q(processed_at__isnull=True),
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_type}:{self.provider_event_id}"
