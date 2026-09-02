import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.booking.constants import BookingStatus, SegmentStatus
from apps.booking.models import Booking
from apps.inventory.constants import FlightStatus
from apps.inventory.models import Flight
from apps.inventory.selectors import sellable_flights_on
from apps.inventory.services.availability import cheapest_open_class

from ..constants import (
    DELAY_THRESHOLD_MINUTES,
    MAX_REBOOK_OPTIONS,
    REBOOK_DAY_OFFSETS,
    REBOOK_OPTION_TTL_HOURS,
    DisruptionType,
)
from ..models import Disruption, RebookOption
from .outbox import emit

logger = logging.getLogger("wayfare.ops")

#: Bookings that still intend to travel. An expired or cancelled one needs no rebooking.
AFFECTED_STATUSES = frozenset(
    {
        BookingStatus.HELD,
        BookingStatus.PENDING_TICKETING,
        BookingStatus.TICKETED,
        BookingStatus.CONFIRMED,
    }
)


def classify(flight: Flight) -> tuple[str, str] | None:
    """What, if anything, is wrong with this flight.

    Returns ``None`` for ordinary operations — a short delay is not something a passenger can
    act on, and telling them about it is noise.
    """
    if flight.status == FlightStatus.CANCELLED:
        return DisruptionType.CANCELLATION, "The airline cancelled this flight."

    if flight.status == FlightStatus.DIVERTED:
        return DisruptionType.DIVERSION, "This flight was diverted."

    if flight.delay_minutes >= DELAY_THRESHOLD_MINUTES:
        return (
            DisruptionType.DELAY,
            f"This flight is delayed by {flight.delay_minutes} minutes.",
        )

    return None


def detect(flight: Flight) -> Disruption | None:
    """Raise a disruption for one flight, once.

    The unique partial index is the guard, not a prior read: the detector runs every five
    minutes and two overlapping runs must not raise the same cancellation twice.
    """
    verdict = classify(flight)
    if verdict is None:
        return None

    kind, reason = verdict

    try:
        with transaction.atomic():
            disruption = Disruption.objects.create(
                flight=flight,
                type=kind,
                reason=reason,
                delay_minutes=flight.delay_minutes,
                detected_at=timezone.now(),
            )
    except IntegrityError:
        return None

    logger.warning(
        "disruption_detected",
        extra={"flight": flight.id, "type": kind, "delay": flight.delay_minutes},
    )
    return disruption


def affected_bookings(flight: Flight):
    """Every booking still holding a live segment on the disrupted flight."""
    return (
        Booking.objects.filter(
            segments__flight=flight,
            status__in=AFFECTED_STATUSES,
        )
        .exclude(segments__flight=flight, segments__status=SegmentStatus.CANCELLED)
        .distinct()
    )


@transaction.atomic
def offer_rebooking(disruption: Disruption, booking: Booking) -> list[RebookOption]:
    """Generate up to three alternatives for one booking and tell the passenger.

    Same day first, then either side of it, same cabin, and the fare difference waived — the
    carrier caused this, so the passenger does not pay for the fix.
    """
    segment = booking.segments.filter(
        flight=disruption.flight, status__in=[SegmentStatus.HELD, SegmentStatus.CONFIRMED]
    ).first()
    if segment is None:
        return []

    seats = booking.passengers.exclude(type="INF").count() or 1
    expires_at = timezone.now() + timedelta(hours=REBOOK_OPTION_TTL_HOURS)
    existing = set(
        booking.rebook_options.values_list("proposed_flight_id", flat=True)
    )

    options: list[RebookOption] = []
    for offset in REBOOK_DAY_OFFSETS:
        if len(options) >= MAX_REBOOK_OPTIONS:
            break

        day = disruption.flight.departure_local.date() + timedelta(days=offset)
        candidates = sellable_flights_on(
            disruption.flight.origin_airport_id,
            disruption.flight.destination_airport_id,
            day,
        ).exclude(id=disruption.flight.id)

        for candidate in candidates:
            if len(options) >= MAX_REBOOK_OPTIONS:
                break
            if candidate.id in existing:
                continue

            availability = cheapest_open_class(candidate.id, segment.cabin, seats)
            if availability is None:
                continue

            options.append(
                RebookOption(
                    disruption=disruption,
                    booking=booking,
                    proposed_flight=candidate,
                    cabin=segment.cabin,
                    rbd=availability.rbd,
                    fare_delta=0,
                    currency=booking.currency,
                    rank=len(options),
                    expires_at=expires_at,
                )
            )
            existing.add(candidate.id)

    RebookOption.objects.bulk_create(options)

    emit(
        "booking",
        booking.pnr,
        "flight_disrupted",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "flight": disruption.flight.designator,
            "type": disruption.type,
            "reason": disruption.reason,
            "options": [
                {
                    "flight": option.proposed_flight.designator,
                    "departure_local": option.proposed_flight.departure_local.isoformat(),
                }
                for option in options
            ],
        },
    )

    logger.info(
        "rebook_options_offered",
        extra={"pnr": booking.pnr, "count": len(options), "flight": disruption.flight_id},
    )
    return options


def sweep(limit: int = 500) -> dict[str, int]:
    """Find newly disrupted flights and offer everyone on them a way out."""
    horizon = timezone.now() - timedelta(hours=6)
    flights = Flight.objects.filter(departure_utc__gte=horizon).filter(
        status__in=[FlightStatus.CANCELLED, FlightStatus.DIVERTED]
    ) | Flight.objects.filter(
        departure_utc__gte=horizon, delay_minutes__gte=DELAY_THRESHOLD_MINUTES
    )

    disruptions = 0
    notified = 0

    for flight in flights.distinct().select_related(
        "origin_airport", "destination_airport", "airline"
    )[:limit]:
        disruption = detect(flight)
        if disruption is None:
            continue

        disruptions += 1
        for booking in affected_bookings(flight):
            offer_rebooking(disruption, booking)
            _mark_disrupted(booking)
            notified += 1

    return {"disruptions": disruptions, "bookings_notified": notified}


def _mark_disrupted(booking: Booking) -> None:
    """Only a ticketed journey moves to DISRUPTED; a mere hold can just expire."""
    from apps.booking.services.state import can_transition, transition

    if can_transition(booking.status, BookingStatus.DISRUPTED):
        transition(booking, BookingStatus.DISRUPTED, reason="flight disrupted")
