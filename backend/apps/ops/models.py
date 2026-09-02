from django.db import models

from apps.common.models import PublicIdModel, TimestampedModel

from .constants import DisruptionType, RebookOptionStatus


class OutboxEvent(TimestampedModel):
    """A side effect promised inside a transaction and delivered after it commits.

    Nothing that leaves the process — email, webhook, PDF, ClickHouse write — happens inline.
    Writing the row is part of the business transaction, so a rollback cannot leave a customer
    holding a confirmation for a booking that does not exist.
    """

    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    available_at = models.DateTimeField(db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["processed_at", "available_at"],
                name="idx_outbox_pending",
                condition=models.Q(processed_at__isnull=True),
            ),
            models.Index(fields=["aggregate_type", "aggregate_id"], name="idx_outbox_aggregate"),
        ]
        ordering = ["available_at"]

    def __str__(self) -> str:
        return f"{self.event_type} {self.aggregate_type}:{self.aggregate_id}"


class AuditLog(TimestampedModel):
    """Who changed what, and what it looked like either side of the change."""

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_entries",
    )
    actor_type = models.CharField(max_length=20, default="SYSTEM")
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=32)
    object_id = models.CharField(max_length=64)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="idx_audit_object"),
            models.Index(fields=["-created_at"], name="idx_audit_recent"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"


class Disruption(PublicIdModel, TimestampedModel):
    """Something happened to a flight that its passengers need to act on."""

    flight = models.ForeignKey(
        "inventory.Flight", on_delete=models.CASCADE, related_name="disruptions"
    )
    type = models.CharField(max_length=20, choices=DisruptionType.choices)
    reason = models.CharField(max_length=255, blank=True)
    delay_minutes = models.IntegerField(default=0)
    detected_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            # One open disruption per flight and type: the detector runs every five minutes
            # and must not raise the same cancellation twelve times an hour.
            models.UniqueConstraint(
                fields=["flight", "type"],
                condition=models.Q(resolved_at__isnull=True),
                name="uniq_open_disruption",
            )
        ]
        indexes = [
            models.Index(fields=["-detected_at"], name="idx_disruption_recent"),
            models.Index(
                fields=["flight"],
                name="idx_disruption_open",
                condition=models.Q(resolved_at__isnull=True),
            ),
        ]
        ordering = ["-detected_at"]

    def __str__(self) -> str:
        return f"{self.type} on flight {self.flight_id}"


class RebookOption(PublicIdModel, TimestampedModel):
    """An alternative flight offered to one disrupted booking.

    It holds no inventory — availability is re-checked when the passenger accepts, because an
    option sitting in an inbox for a day is a suggestion, not a reservation.
    """

    disruption = models.ForeignKey(
        Disruption, on_delete=models.CASCADE, related_name="options"
    )
    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.CASCADE, related_name="rebook_options"
    )
    proposed_flight = models.ForeignKey(
        "inventory.Flight", on_delete=models.CASCADE, related_name="rebook_options"
    )
    cabin = models.CharField(max_length=16)
    rbd = models.CharField(max_length=1)
    #: Always zero today: a carrier-caused disruption waives the difference (SPEC.md §6.5).
    fare_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    rank = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=RebookOptionStatus.choices, default=RebookOptionStatus.OFFERED
    )
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "proposed_flight"], name="uniq_option_per_flight"
            )
        ]
        indexes = [models.Index(fields=["booking", "status"], name="idx_option_booking")]
        ordering = ["rank", "proposed_flight__departure_utc"]

    def __str__(self) -> str:
        return f"{self.booking_id} → flight {self.proposed_flight_id} ({self.status})"
