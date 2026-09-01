from datetime import date

from django.db.models import QuerySet
from django.utils import timezone

from .constants import SELLABLE_FLIGHT_STATUSES
from .models import Flight, Seat


def flights_base() -> QuerySet[Flight]:
    return Flight.objects.select_related(
        "airline", "origin_airport", "destination_airport", "aircraft"
    ).prefetch_related("cabins", "booking_classes")


def sellable_flights_on(origin: str, destination: str, day: date) -> QuerySet[Flight]:
    """Flights departing on a local calendar day at the origin.

    The window is built in UTC around the origin's day so a late-evening departure is not lost
    to the timezone offset.
    """
    # Match on the airport wall clock, not a padded UTC window: "flights on the 8th" means the
    # local calendar day at the origin. A UTC window wide enough to cover every offset spans
    # ~52 hours and pulls in the next day's operation of the same flight number.
    return (
        flights_base()
        .filter(
            origin_airport_id=origin.upper(),
            destination_airport_id=destination.upper(),
            departure_local__date=day,
            departure_utc__gte=timezone.now(),
            status__in=SELLABLE_FLIGHT_STATUSES,
        )
        .order_by("departure_utc")
    )


def connections_from(origin: str, day: date) -> QuerySet[Flight]:
    """All sellable departures from an airport on a day — the first hop of a connection search."""
    return (
        flights_base()
        .filter(
            origin_airport_id=origin.upper(),
            departure_local__date=day,
            departure_utc__gte=timezone.now(),
            status__in=SELLABLE_FLIGHT_STATUSES,
        )
        .order_by("departure_utc")
    )


def onward_flights(origin: str, after, until) -> QuerySet[Flight]:
    return (
        flights_base()
        .filter(
            origin_airport_id=origin,
            departure_utc__gte=after,
            departure_utc__lte=until,
            status__in=SELLABLE_FLIGHT_STATUSES,
        )
        .order_by("departure_utc")
    )


def seats_for(flight_id: int, cabin: str = "") -> QuerySet[Seat]:
    qs = Seat.objects.filter(flight_id=flight_id, is_blocked=False)
    if cabin:
        qs = qs.filter(cabin=cabin)
    return qs.order_by("row", "column")
