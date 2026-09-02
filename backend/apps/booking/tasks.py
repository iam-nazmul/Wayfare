import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.common.locks import LockNotAcquired, redis_lock
from apps.inventory.services.availability import SeatRequest, release
from apps.ops.services.outbox import emit

from .constants import BookingStatus
from .models import Booking, Offer
from .services.change import abandon_change
from .services.state import transition

logger = logging.getLogger("wayfare.booking")


@shared_task(name="booking.expire_offers", queue="default")
def expire_offers(batch: int = 5000) -> int:
    """Delete offers past their TTL.

    Offers are kept only for audit and the fare calendar; once expired they cannot be booked, so
    holding them costs storage and slows the calendar aggregate.
    """
    cutoff = timezone.now()
    ids = list(
        Offer.objects.filter(expires_at__lt=cutoff).values_list("id", flat=True)[:batch]
    )
    if not ids:
        return 0

    deleted, _ = Offer.objects.filter(id__in=ids).delete()
    logger.info("offers_expired", extra={"count": deleted})
    return deleted


@shared_task(name="booking.release_expired_holds", queue="critical", acks_late=True)
def release_expired_holds(batch: int = 200) -> int:
    """Give back the seats behind holds that ran out of time, and expire their bookings.

    One booking per transaction and per Redis lock: a payment webhook landing on the same PNR
    at the same moment must not find half its holds released. State is re-read inside the
    transaction, so a booking that got paid for while this task queued is left alone.
    """
    cutoff = timezone.now()
    pnrs = list(
        Booking.objects.filter(
            status__in=[BookingStatus.HELD, BookingStatus.CHANGE_PENDING],
            hold_expires_at__lt=cutoff,
        ).values_list("pnr", flat=True)[:batch]
    )

    released = 0
    for pnr in pnrs:
        try:
            with redis_lock(f"booking:{pnr}", timeout=30):
                released += _release_one(pnr)
        except LockNotAcquired:
            logger.info("hold_release_skipped_locked", extra={"pnr": pnr})

    if released:
        logger.info("holds_released", extra={"count": released})
    return released


@transaction.atomic
def _release_one(pnr: str) -> int:
    booking = Booking.objects.select_for_update().filter(pnr=pnr).first()
    if booking is None or booking.status not in {
        BookingStatus.HELD,
        BookingStatus.CHANGE_PENDING,
    }:
        return 0
    if booking.hold_expires_at is None or booking.hold_expires_at >= timezone.now():
        return 0

    if booking.status == BookingStatus.CHANGE_PENDING:
        # An unpaid exchange: drop the proposed seats and leave the passenger on the ticket
        # they already hold, rather than expiring a journey they have already paid for.
        abandon_change(booking)
        return 1

    holds = list(booking.holds.filter(released_at__isnull=True))
    if holds:
        release(
            [
                SeatRequest(
                    flight_id=hold.flight_id,
                    cabin=hold.cabin,
                    rbd=hold.rbd,
                    seats=hold.seats,
                )
                for hold in holds
            ]
        )
        booking.holds.filter(id__in=[hold.id for hold in holds]).update(
            released_at=timezone.now()
        )

    transition(booking, BookingStatus.EXPIRED, reason="hold expired")
    emit(
        "booking",
        booking.pnr,
        "booking_expired",
        {"pnr": booking.pnr, "contact_email": booking.contact_email},
    )
    return 1
