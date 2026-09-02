from django.db import models


class TicketStatus(models.TextChoices):
    ISSUED = "ISSUED", "Issued"
    EXCHANGED = "EXCHANGED", "Exchanged"
    REFUNDED = "REFUNDED", "Refunded"
    VOID = "VOID", "Void"


class CouponStatus(models.TextChoices):
    OPEN = "OPEN", "Open for use"
    CHECKED_IN = "CHECKED_IN", "Checked in"
    LIFTED = "LIFTED", "Lifted"
    FLOWN = "FLOWN", "Flown"
    EXCHANGED = "EXCHANGED", "Exchanged"
    REFUNDED = "REFUNDED", "Refunded"
    VOID = "VOID", "Void"


class TicketEventType(models.TextChoices):
    ISSUED = "ISSUED", "Issued"
    VOIDED = "VOIDED", "Voided"
    EXCHANGED = "EXCHANGED", "Exchanged"
    REFUNDED = "REFUNDED", "Refunded"
    COUPON_USED = "COUPON_USED", "Coupon used"


#: A ticket may only be voided on its day of issue, and only while every coupon is still OPEN.
VOIDABLE_COUPON_STATUSES = frozenset({CouponStatus.OPEN})

#: A confirmed booking that never got its tickets is money taken for nothing — chase it.
UNTICKETED_ALERT_MINUTES = 30
