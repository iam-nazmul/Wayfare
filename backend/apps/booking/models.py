import uuid

from django.db import models

from apps.accounts.constants import DocumentType, Gender
from apps.common.models import PublicIdModel, TimestampedModel
from apps.inventory.constants import Cabin
from apps.pricing.constants import PassengerType, TripType

from .constants import BookingStatus, SegmentStatus, SourceChannel


class SearchQuery(PublicIdModel, TimestampedModel):
    """Thin record of an executed search. The rich analytics row goes to ClickHouse."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="searches",
    )
    session_id = models.CharField(max_length=64, blank=True)
    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    depart_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    trip_type = models.CharField(max_length=12, choices=TripType.choices)
    pax_adults = models.PositiveSmallIntegerField(default=1)
    pax_children = models.PositiveSmallIntegerField(default=0)
    pax_infants = models.PositiveSmallIntegerField(default=0)
    cabin = models.CharField(max_length=16, choices=Cabin.choices, default=Cabin.ECONOMY)
    currency = models.CharField(max_length=3, default="USD")
    results_count = models.PositiveSmallIntegerField(default=0)
    cache_hit = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(
                fields=["origin", "destination", "depart_date"], name="idx_search_market"
            ),
            models.Index(fields=["-created_at"], name="idx_search_recent"),
        ]
        verbose_name_plural = "search queries"

    def __str__(self) -> str:
        return f"{self.origin}-{self.destination} {self.depart_date}"


class Offer(TimestampedModel):
    """A priced, signed, time-limited search result.

    An offer holds no inventory. It is re-validated — signature, expiry and live availability —
    at booking time.
    """

    offer_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    search_query = models.ForeignKey(
        SearchQuery, on_delete=models.CASCADE, related_name="offers"
    )
    itinerary = models.JSONField(default=dict)
    price_breakdown = models.JSONField(default=dict)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    fare_family = models.ForeignKey(
        "pricing.FareFamily", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="offers",
    )
    seats_remaining = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    #: HMAC over the priced payload — a client cannot alter an offer before booking it.
    signature = models.CharField(max_length=64)

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"], name="idx_offer_expiry"),
            models.Index(fields=["search_query", "total_amount"], name="idx_offer_price"),
        ]
        ordering = ["total_amount"]

    def __str__(self) -> str:
        return f"{self.offer_id} {self.total_amount} {self.currency}"


class Booking(PublicIdModel, TimestampedModel):
    """A held or sold journey, addressed publicly by its PNR.

    Never assign ``status`` directly — go through ``services/state.py::transition``, which is
    where the legal state machine and the audit trail live.
    """

    pnr = models.CharField(max_length=6, unique=True)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bookings",
    )
    agency = models.ForeignKey(
        "accounts.Agency", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bookings",
    )
    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.DRAFT
    )
    trip_type = models.CharField(
        max_length=12, choices=TripType.choices, default=TripType.ONE_WAY
    )
    currency = models.CharField(max_length=3, default="USD")
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ancillary_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=32, blank=True)
    promo_code = models.ForeignKey(
        "pricing.PromoCode", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bookings",
    )
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    booked_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    source_channel = models.CharField(
        max_length=10, choices=SourceChannel.choices, default=SourceChannel.WEB
    )
    version = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [
            models.Index(fields=["contact_email"], name="idx_booking_contact"),
            models.Index(fields=["status", "hold_expires_at"], name="idx_booking_hold"),
            models.Index(fields=["-created_at"], name="idx_booking_recent"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pnr} ({self.status})"

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount


class BookingSegment(TimestampedModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="segments")
    flight = models.ForeignKey(
        "inventory.Flight", on_delete=models.PROTECT, related_name="booking_segments"
    )
    sequence = models.PositiveSmallIntegerField()
    cabin = models.CharField(max_length=16, choices=Cabin.choices)
    rbd = models.CharField(max_length=1)
    fare_basis = models.CharField(max_length=16, blank=True)
    fare_family = models.ForeignKey(
        "pricing.FareFamily", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="booking_segments",
    )
    marketing_flight_number = models.CharField(max_length=8)
    status = models.CharField(
        max_length=12, choices=SegmentStatus.choices, default=SegmentStatus.HELD
    )
    baggage_allowance = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "sequence"], name="uniq_segment_sequence"
            )
        ]
        indexes = [models.Index(fields=["flight"], name="idx_segment_flight")]
        ordering = ["sequence"]

    def __str__(self) -> str:
        return f"{self.marketing_flight_number} seq {self.sequence}"


class Passenger(TimestampedModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="passengers")
    type = models.CharField(max_length=3, choices=PassengerType.choices)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    dob = models.DateField()
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    nationality = models.CharField(max_length=2, blank=True)
    doc_type = models.CharField(max_length=20, choices=DocumentType.choices, blank=True)
    doc_number = models.CharField(max_length=64, blank=True)
    doc_expiry = models.DateField(null=True, blank=True)
    frequent_flyer_number = models.CharField(max_length=32, blank=True)
    #: An infant has no seat of its own and travels on this adult's lap.
    associated_adult = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="infants"
    )

    class Meta:
        indexes = [models.Index(fields=["last_name"], name="idx_passenger_surname")]
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.last_name}/{self.first_name} ({self.type})"


class InventoryHold(TimestampedModel):
    """The seats a booking has taken out of inventory, and when they come back.

    One row per segment. ``released_at`` is set by whatever gives the seats back — hold
    expiry, cancellation — so a hold is never reversed twice.
    """

    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, null=True, blank=True, related_name="holds"
    )
    offer_id = models.UUIDField()
    flight = models.ForeignKey(
        "inventory.Flight", on_delete=models.PROTECT, related_name="holds"
    )
    cabin = models.CharField(max_length=16, choices=Cabin.choices)
    rbd = models.CharField(max_length=1)
    seats = models.PositiveSmallIntegerField()
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    hold_key = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["expires_at"],
                name="idx_hold_expiry",
                condition=models.Q(released_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.seats} seat(s) {self.cabin}/{self.rbd} on flight {self.flight_id}"
