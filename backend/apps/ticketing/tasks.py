import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.common.exceptions import InvalidTransition
from apps.common.locks import LockNotAcquired, redis_lock

from .constants import UNTICKETED_ALERT_MINUTES
from .services.exchange import exchange_tickets as exchange
from .services.issue import issue_tickets as issue

logger = logging.getLogger("wayfare.ticketing")


@shared_task(
    name="ticketing.issue_tickets",
    queue="critical",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def issue_tickets(booking_id: int) -> int:
    """Issue e-tickets for a paid booking.

    Keyed by booking id and safe to redeliver: `issue()` returns the existing tickets rather
    than allocating a second set of ticket numbers.
    """
    booking = Booking.objects.filter(pk=booking_id).first()
    if booking is None:
        return 0

    try:
        with redis_lock(f"booking:{booking.pnr}", timeout=60):
            tickets = issue(booking)
    except LockNotAcquired:
        logger.info("ticketing_lock_busy", extra={"pnr": booking.pnr})
        raise
    except InvalidTransition:
        # The booking moved on — cancelled before ticketing, or already ticketed by another
        # delivery. Neither is retryable.
        logger.info("ticketing_skipped", extra={"pnr": booking.pnr, "status": booking.status})
        return 0

    return len(tickets)


@shared_task(name="ticketing.void_expired_unticketed", queue="critical")
def void_expired_unticketed() -> int:
    """Surface bookings that took money but never got tickets.

    Nothing is voided automatically: money has changed hands, so this raises the alarm for the
    ticketing desk rather than making the decision itself.
    """
    cutoff = timezone.now() - timedelta(minutes=UNTICKETED_ALERT_MINUTES)
    stuck = list(
        Booking.objects.filter(
            status=BookingStatus.PENDING_TICKETING, updated_at__lt=cutoff
        ).values_list("pnr", flat=True)[:200]
    )

    if stuck:
        logger.error("bookings_paid_but_unticketed", extra={"pnrs": stuck, "count": len(stuck)})

    return len(stuck)


@shared_task(
    name="ticketing.exchange_tickets",
    queue="critical",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def exchange_tickets(booking_id: int) -> int:
    """Reissue tickets after a change has been paid for.

    Keyed by booking id and safe to redeliver: `exchange()` refuses anything that is no longer
    `CHANGE_PENDING`, so a second delivery finds the work already done.
    """
    booking = Booking.objects.filter(pk=booking_id).first()
    if booking is None:
        return 0

    try:
        with redis_lock(f"booking:{booking.pnr}", timeout=60):
            tickets = exchange(booking)
    except LockNotAcquired:
        logger.info("exchange_lock_busy", extra={"pnr": booking.pnr})
        raise
    except InvalidTransition:
        logger.info("exchange_skipped", extra={"pnr": booking.pnr, "status": booking.status})
        return 0

    return len(tickets)
