import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from .constants import FlightStatus
from .models import Flight
from .services.materialise import materialise_all

logger = logging.getLogger("wayfare.inventory")


@shared_task(name="inventory.materialise_schedules", queue="default")
def materialise_schedules(days: int = 365) -> dict[str, int]:
    """Extend the dated-flight horizon. Safe to re-run: existing dates hit the unique constraint."""
    totals = materialise_all(days=days)
    logger.info("schedules_materialised", extra=totals)
    return totals


@shared_task(name="inventory.mark_departed_flights", queue="default")
def mark_departed_flights() -> int:
    """Advance flights past their departure and arrival times.

    Uses two bounded updates rather than per-row saves — this runs every 10 minutes against the
    whole future schedule.
    """
    now = timezone.now()

    departed = Flight.objects.filter(
        Q(status__in=[FlightStatus.SCHEDULED, FlightStatus.DELAYED, FlightStatus.BOARDING]),
        departure_utc__lt=now,
    ).update(status=FlightStatus.DEPARTED, updated_at=now)

    arrived = Flight.objects.filter(
        status=FlightStatus.DEPARTED, arrival_utc__lt=now
    ).update(status=FlightStatus.ARRIVED, updated_at=now)

    return departed + arrived


@shared_task(name="inventory.recalculate_availability", queue="default")
def recalculate_availability(flight_id: int) -> None:
    """Sweep cached search results for a flight's route after an inventory or fare change."""
    from apps.inventory.services.cache import invalidate_flight

    invalidate_flight(flight_id)
