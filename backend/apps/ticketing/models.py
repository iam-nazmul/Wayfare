from django.db import models

from apps.common.models import PublicIdModel, TimestampedModel

from .constants import CouponStatus, TicketEventType, TicketStatus


class TicketSerial(TimestampedModel):
    """Per-airline ticket serial counter. See ``services/numbers.py::next_ticket_number``."""

    airline_prefix = models.CharField(max_length=3, primary_key=True)
    last_serial = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.airline_prefix} @ {self.last_serial}"


class Ticket(PublicIdModel, TimestampedModel):
    """One e-ticket per passenger, with one coupon per flown segment."""

    ticket_number = models.CharField(max_length=13, unique=True)
    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.PROTECT, related_name="tickets"
    )
    passenger = models.ForeignKey(
        "booking.Passenger", on_delete=models.PROTECT, related_name="tickets"
    )
    issuing_airline = models.ForeignKey(
        "catalog.Airline", on_delete=models.PROTECT, related_name="tickets"
    )
    issued_at = models.DateTimeField()
    issued_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tickets_issued",
    )
    status = models.CharField(
        max_length=12, choices=TicketStatus.choices, default=TicketStatus.ISSUED
    )
    fare_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    fare_calculation = models.TextField(blank=True)
    conjunction_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="conjunctions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "passenger"],
                condition=models.Q(status="ISSUED"),
                name="uniq_live_ticket_per_passenger",
            )
        ]
        indexes = [models.Index(fields=["booking"], name="idx_ticket_booking")]
        ordering = ["ticket_number"]

    def __str__(self) -> str:
        return self.ticket_number


class TicketCoupon(TimestampedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="coupons")
    segment = models.ForeignKey(
        "booking.BookingSegment", on_delete=models.PROTECT, related_name="coupons"
    )
    coupon_number = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12, choices=CouponStatus.choices, default=CouponStatus.OPEN
    )
    flown_at = models.DateTimeField(null=True, blank=True)
    exchanged_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="exchanged_from"
    )
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "coupon_number"], name="uniq_coupon_number"
            )
        ]
        ordering = ["coupon_number"]

    def __str__(self) -> str:
        return f"{self.ticket.ticket_number}/{self.coupon_number} ({self.status})"


class TicketEvent(TimestampedModel):
    """Append-only history of what happened to a ticket."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=16, choices=TicketEventType.choices)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ticket_events",
    )
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["ticket", "created_at"], name="idx_ticket_event")]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.event_type} {self.ticket_id}"
