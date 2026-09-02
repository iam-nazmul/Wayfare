import logging

from django.db import transaction
from django.utils import timezone

from ..constants import CouponStatus, TicketEventType, TicketStatus
from ..models import Ticket, TicketEvent

logger = logging.getLogger("wayfare.ticketing")

#: A coupon that has already been used cannot be refunded — the passenger flew on it.
REFUNDABLE_COUPON_STATUSES = frozenset({CouponStatus.OPEN, CouponStatus.CHECKED_IN})


@transaction.atomic
def refund_coupons(booking) -> int:
    """Close out the coupons behind a refunded booking.

    Only unused coupons are refunded; a flown one stays `FLOWN` so the revenue it earned is
    still visible. A ticket keeps `ISSUED` until every coupon is closed.
    """
    now = timezone.now()
    closed = 0

    for ticket in Ticket.objects.filter(booking=booking, status=TicketStatus.ISSUED):
        affected = ticket.coupons.filter(status__in=REFUNDABLE_COUPON_STATUSES)
        closed += affected.update(status=CouponStatus.REFUNDED, refunded_at=now)

        if not ticket.coupons.exclude(status=CouponStatus.REFUNDED).exists():
            Ticket.objects.filter(pk=ticket.pk).update(status=TicketStatus.REFUNDED)

        TicketEvent.objects.create(
            ticket=ticket,
            event_type=TicketEventType.REFUNDED,
            payload={"coupons": closed, "pnr": booking.pnr},
        )

    if closed:
        logger.info("coupons_refunded", extra={"pnr": booking.pnr, "coupons": closed})

    return closed
