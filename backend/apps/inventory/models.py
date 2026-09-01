from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q

from apps.common.models import PublicIdModel, TimestampedModel

from .constants import (
    Cabin,
    FlightStatus,
    ScheduleStatus,
    SeatStatus,
)


class Route(TimestampedModel):
    airline = models.ForeignKey("catalog.Airline", on_delete=models.CASCADE, related_name="routes")
    origin_airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.PROTECT, related_name="routes_out"
    )
    destination_airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.PROTECT, related_name="routes_in"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["airline", "origin_airport", "destination_airport"], name="uniq_route"
            ),
            models.CheckConstraint(
                condition=~Q(origin_airport=F("destination_airport")),
                name="route_origin_ne_destination",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.origin_airport_id}-{self.destination_airport_id}"


class SeatMapTemplate(TimestampedModel):
    name = models.CharField(max_length=100)
    aircraft = models.ForeignKey(
        "catalog.Aircraft", on_delete=models.PROTECT, related_name="seat_maps"
    )
    #: {"cabins": [{"cabin": "ECONOMY", "rows": [10, 40], "columns": "ABC DEF",
    #:   "exit_rows": [14], "pitch": 30}]}
    layout = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.name


class FlightSchedule(TimestampedModel):
    """A repeating pattern, authored in local time, materialised into dated Flight rows."""

    airline = models.ForeignKey(
        "catalog.Airline", on_delete=models.CASCADE, related_name="schedules"
    )
    flight_number = models.CharField(max_length=5)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="schedules")
    aircraft = models.ForeignKey(
        "catalog.Aircraft", on_delete=models.PROTECT, related_name="schedules"
    )
    seat_map_template = models.ForeignKey(
        SeatMapTemplate, on_delete=models.PROTECT, related_name="schedules"
    )
    dep_time_local = models.TimeField()
    arr_time_local = models.TimeField()
    #: 1 when the flight lands the next local day. Dropping this yields negative durations.
    arrival_day_offset = models.PositiveSmallIntegerField(default=0)
    #: Monday=index 0 … Sunday=index 6.
    days_of_week = ArrayField(models.BooleanField(), size=7, default=list)
    effective_from = models.DateField()
    effective_to = models.DateField()
    status = models.CharField(
        max_length=12, choices=ScheduleStatus.choices, default=ScheduleStatus.ACTIVE
    )
    default_cabin_capacity = models.JSONField(
        default=dict, help_text='{"ECONOMY": 162, "BUSINESS": 18}'
    )

    class Meta:
        indexes = [
            models.Index(fields=["airline", "flight_number"], name="idx_schedule_flightno"),
            models.Index(fields=["status", "effective_to"], name="idx_schedule_active"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__gte=F("effective_from")),
                name="schedule_effective_range_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.airline_id}{self.flight_number}"

    def operates_on(self, weekday: int) -> bool:
        return bool(self.days_of_week[weekday]) if len(self.days_of_week) == 7 else True


class Flight(PublicIdModel, TimestampedModel):
    schedule = models.ForeignKey(
        FlightSchedule, on_delete=models.SET_NULL, null=True, blank=True, related_name="flights"
    )
    airline = models.ForeignKey("catalog.Airline", on_delete=models.PROTECT, related_name="flights")
    flight_number = models.CharField(max_length=5)
    origin_airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.PROTECT, related_name="departures"
    )
    destination_airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.PROTECT, related_name="arrivals"
    )
    aircraft = models.ForeignKey("catalog.Aircraft", on_delete=models.PROTECT, related_name="flights")
    seat_map_template = models.ForeignKey(
        SeatMapTemplate, on_delete=models.PROTECT, related_name="flights"
    )

    departure_utc = models.DateTimeField()
    arrival_utc = models.DateTimeField()
    #: Naive local wall-clock at each airport — what the passenger reads on the boarding pass.
    departure_local = models.DateTimeField()
    arrival_local = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()

    status = models.CharField(
        max_length=12, choices=FlightStatus.choices, default=FlightStatus.SCHEDULED
    )
    gate = models.CharField(max_length=8, blank=True)
    terminal = models.CharField(max_length=8, blank=True)
    actual_departure_utc = models.DateTimeField(null=True, blank=True)
    delay_minutes = models.IntegerField(default=0)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["airline", "flight_number", "departure_utc"], name="uniq_flight_departure"
            ),
            models.CheckConstraint(
                condition=Q(arrival_utc__gt=F("departure_utc")), name="flight_arrives_after_departure"
            ),
        ]
        indexes = [
            models.Index(
                fields=["origin_airport", "destination_airport", "departure_utc"],
                name="idx_flight_od_date",
            ),
            models.Index(
                fields=["departure_utc"],
                condition=Q(status__in=["SCHEDULED", "DELAYED"]),
                name="idx_flight_sellable",
            ),
            models.Index(fields=["schedule", "departure_utc"], name="idx_flight_schedule"),
        ]
        ordering = ["departure_utc"]

    def __str__(self) -> str:
        return f"{self.airline_id}{self.flight_number} {self.departure_utc:%Y-%m-%d}"

    @property
    def designator(self) -> str:
        return f"{self.airline_id}{self.flight_number}"


class CabinConfig(TimestampedModel):
    """Physical capacity per cabin. This is the hard ceiling — RBD authorisations are not."""

    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name="cabins")
    cabin = models.CharField(max_length=16, choices=Cabin.choices)
    capacity = models.PositiveSmallIntegerField()
    seats_sold = models.PositiveSmallIntegerField(default=0)
    seats_held = models.PositiveSmallIntegerField(default=0)
    oversell_allowance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["flight", "cabin"], name="uniq_flight_cabin"),
            models.CheckConstraint(
                condition=Q(seats_sold__gte=0) & Q(seats_held__gte=0),
                name="cabin_counts_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(seats_sold__lte=F("capacity") + F("oversell_allowance")),
                name="cabin_not_oversold",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.flight_id}:{self.cabin}"

    @property
    def seats_available(self) -> int:
        return max(0, self.capacity + self.oversell_allowance - self.seats_sold - self.seats_held)


class BookingClass(TimestampedModel):
    """One RBD bucket. ``authorised`` may sum above cabin capacity — that nesting is intentional."""

    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name="booking_classes")
    cabin_config = models.ForeignKey(
        CabinConfig, on_delete=models.CASCADE, related_name="booking_classes"
    )
    rbd = models.CharField(max_length=1)
    authorised = models.PositiveSmallIntegerField(default=0)
    sold = models.PositiveSmallIntegerField(default=0)
    held = models.PositiveSmallIntegerField(default=0)
    is_open = models.BooleanField(default=True)
    #: 0 = most expensive bucket in the cabin.
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["flight", "rbd"], name="uniq_flight_rbd"),
            models.CheckConstraint(
                condition=Q(sold__lte=F("authorised")), name="rbd_not_oversold"
            ),
            models.CheckConstraint(
                condition=Q(sold__gte=0) & Q(held__gte=0), name="rbd_counts_non_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["flight", "sort_order"], name="idx_rbd_ladder"),
        ]
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return f"{self.flight_id}:{self.rbd}"

    @property
    def seats_available(self) -> int:
        return max(0, self.authorised - self.sold - self.held)


class Seat(TimestampedModel):
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name="seats")
    cabin = models.CharField(max_length=16, choices=Cabin.choices)
    row = models.PositiveSmallIntegerField()
    column = models.CharField(max_length=1)
    seat_number = models.CharField(max_length=4)
    characteristics = ArrayField(models.CharField(max_length=20), default=list, blank=True)
    is_exit_row = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    seat_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    seat_fee_currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=12, choices=SeatStatus.choices, default=SeatStatus.AVAILABLE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["flight", "seat_number"], name="uniq_flight_seat"),
        ]
        indexes = [
            models.Index(fields=["flight", "cabin", "status"], name="idx_seat_availability"),
        ]
        ordering = ["row", "column"]

    def __str__(self) -> str:
        return f"{self.flight_id}:{self.seat_number}"


class ScheduleMaterialisation(TimestampedModel):
    """Audit of which window of a schedule has been turned into flights."""

    schedule = models.ForeignKey(
        FlightSchedule, on_delete=models.CASCADE, related_name="materialisations"
    )
    window_start = models.DateField()
    window_end = models.DateField()
    flights_created = models.PositiveIntegerField(default=0)
    flights_skipped = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["schedule", "-window_end"], name="idx_materialisation_window"),
        ]
