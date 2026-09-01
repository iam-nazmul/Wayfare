import logging

from celery import shared_task
from django.utils import timezone

from .models import Offer

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


@shared_task(name="booking.release_expired_holds", queue="critical")
def release_expired_holds() -> int:
    """Reverse holds past their TTL. Implemented with M3, when holds exist."""
    return 0
