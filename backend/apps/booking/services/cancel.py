import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import InvalidTransition
from apps.inventory.services.availability import SeatRequest, release, unsell
from apps.ops.services.outbox import emit
from apps.pricing.services.refunds import RefundQuote, quote_refund

from ..constants import BookingStatus, SegmentStatus
from ..models import Booking
from .state import transition

logger = logging.getLogger("wayfare.booking")

#: A booking can be cancelled from any of these; anything else is already finished.
CANCELLABLE = frozenset(
    {
        BookingStatus.HELD,
        BookingStatus.PENDING_TICKETING,
        BookingStatus.TICKETED,
        BookingStatus.CONFIRMED,
    }
)

#: Statuses whose seats are sold rather than merely held.
SOLD_STATUSES = frozenset(
    {BookingStatus.PENDING_TICKETING, BookingStatus.TICKETED, BookingStatus.CONFIRMED}
)


@dataclass(frozen=True, slots=True)
class CancellationResult:
    booking: Booking
    quote: RefundQuote
    refund: object | None = None
    voided: bool = False


def is_voidable(booking: Booking, *, now=None) -> bool:
    """Void window: same calendar day as issue, with every coupon still unused.

    A void is not a refund — nothing was reported to the airline's revenue accounting yet, so
    the money is returned in full with no penalty.
    """
    if booking.status not in {BookingStatus.TICKETED, BookingStatus.PENDING_TICKETING}:
        return False

    ticket = booking.tickets.filter(status="ISSUED").order_by("issued_at").first()
    if ticket is None:
        return booking.status == BookingStatus.PENDING_TICKETING

    today = (now or timezone.now()).date()
    if ticket.issued_at.date() != today:
        return False

    from apps.ticketing.constants import CouponStatus

    return not ticket.coupons.exclude(status=CouponStatus.OPEN).exists()


@transaction.atomic
def cancel_booking(booking: Booking, *, actor=None, reason: str = "") -> CancellationResult:
    """Cancel a booking, release its seats, and open a refund for whatever is owed back.

    The seats go back first and unconditionally: whether the money returns is a fare-rule
    question that can wait for an approver, but an inventory row held by a cancelled booking is
    a seat nobody can sell.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)

    if booking.status not in CANCELLABLE:
        raise InvalidTransition(f"A {booking.status} booking cannot be cancelled.")

    voided = is_voidable(booking)
    quote = quote_refund(booking)

    if voided:
        quote = _void_quote(booking, quote)

    _release_inventory(booking)
    booking.segments.update(status=SegmentStatus.CANCELLED)

    transition(booking, BookingStatus.CANCELLED, actor=actor, reason=reason or "cancelled")

    refund = None
    if quote.refundable.amount > 0:
        from apps.payments.services.refunds import request_refund

        transition(
            booking, BookingStatus.REFUND_PENDING, actor=actor, reason="refund raised"
        )
        refund = request_refund(booking, quote, actor=actor, reason=reason)

    emit(
        "booking",
        booking.pnr,
        "booking_cancelled",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "voided": voided,
            "refundable": quote.refundable.as_dict(),
            "penalty": quote.penalty.as_dict(),
        },
    )

    logger.info(
        "booking_cancelled",
        extra={
            "pnr": booking.pnr,
            "voided": voided,
            "refundable": str(quote.refundable.amount),
        },
    )

    return CancellationResult(
        booking=booking, quote=quote, refund=refund, voided=voided
    )


def _void_quote(booking: Booking, quote: RefundQuote) -> RefundQuote:
    """Inside the void window the whole amount comes back, penalty-free."""
    from apps.common.money import Money

    return RefundQuote(
        currency=quote.currency,
        paid=quote.paid,
        penalty=Money.zero(quote.currency),
        non_refundable_tax=Money.zero(quote.currency),
        refundable=quote.paid,
        refundable_fare=True,
        reason="Voided on the day of issue — no penalty applies.",
        tax_lines=quote.tax_lines,
    )


def _release_inventory(booking: Booking) -> None:
    """Give the seats back, from wherever they currently sit."""
    holds = list(booking.holds.filter(released_at__isnull=True))
    was_sold = booking.status in SOLD_STATUSES

    if holds:
        requests = [
            SeatRequest(
                flight_id=hold.flight_id,
                cabin=hold.cabin,
                rbd=hold.rbd,
                seats=hold.seats,
            )
            for hold in holds
        ]
        release(requests)
        booking.holds.filter(id__in=[hold.id for hold in holds]).update(
            released_at=timezone.now()
        )
        return

    if not was_sold:
        return

    # Paid bookings have no live holds — the seats were converted to sales at capture, so they
    # come back out of `sold` instead.
    seats = booking.passengers.exclude(type="INF").count() or 1
    unsell(
        [
            SeatRequest(
                flight_id=segment.flight_id,
                cabin=segment.cabin,
                rbd=segment.rbd,
                seats=seats,
            )
            for segment in booking.segments.all()
        ]
    )
