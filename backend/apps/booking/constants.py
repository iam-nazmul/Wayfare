from django.db import models


class BookingStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    HELD = "HELD", "Held"
    PENDING_TICKETING = "PENDING_TICKETING", "Pending ticketing"
    TICKETED = "TICKETED", "Ticketed"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CHANGE_PENDING = "CHANGE_PENDING", "Change pending"
    DISRUPTED = "DISRUPTED", "Disrupted"
    REBOOKED = "REBOOKED", "Rebooked"
    CANCELLED = "CANCELLED", "Cancelled"
    REFUND_PENDING = "REFUND_PENDING", "Refund pending"
    REFUNDED = "REFUNDED", "Refunded"
    EXPIRED = "EXPIRED", "Expired"


class SegmentStatus(models.TextChoices):
    HELD = "HELD", "Held"
    CONFIRMED = "CONFIRMED", "Confirmed"
    FLOWN = "FLOWN", "Flown"
    CANCELLED = "CANCELLED", "Cancelled"


class SourceChannel(models.TextChoices):
    WEB = "WEB", "Web"
    AGENCY = "AGENCY", "Agency"
    OPS = "OPS", "Ops"


#: No I or O — they are indistinguishable from 1 and 0 when a PNR is read aloud or handwritten.
PNR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
PNR_LENGTH = 6
PNR_MAX_ATTEMPTS = 5
