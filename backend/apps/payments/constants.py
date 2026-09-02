from django.db import models


class IntentStatus(models.TextChoices):
    REQUIRES_PAYMENT = "REQUIRES_PAYMENT", "Requires payment method"
    REQUIRES_ACTION = "REQUIRES_ACTION", "Requires customer action (3DS)"
    PROCESSING = "PROCESSING", "Processing"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentStatus(models.TextChoices):
    AUTHORISED = "AUTHORISED", "Authorised"
    CAPTURED = "CAPTURED", "Captured"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially refunded"


class RefundStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"


class ThreeDsStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"
    REQUIRED = "REQUIRED", "Required"
    AUTHENTICATED = "AUTHENTICATED", "Authenticated"
    FAILED = "FAILED", "Failed"


class LedgerEntryType(models.TextChoices):
    SALE = "SALE", "Sale"
    PAYMENT = "PAYMENT", "Payment"
    REFUND = "REFUND", "Refund"
    PENALTY = "PENALTY", "Penalty"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class CaptureMethod(models.TextChoices):
    AUTOMATIC = "AUTOMATIC", "Automatic"
    MANUAL = "MANUAL", "Manual"


#: How long a client has to complete an intent before it is abandoned. Shorter than the 20-minute
#: hold, so a stalled payment does not outlive the seats it is paying for.
INTENT_TTL_MINUTES = 15

#: If the provider's webhook has not arrived by then, go and ask it directly.
RECONCILE_AFTER_SECONDS = 180
