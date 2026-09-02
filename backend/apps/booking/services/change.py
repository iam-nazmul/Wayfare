import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import FareRuleViolation, InvalidTransition
from apps.common.money import Money
from apps.inventory.models import Flight
from apps.inventory.services.availability import SeatRequest, hold, release
from apps.ops.services.outbox import emit

from ..constants import BookingStatus, SegmentStatus
from ..models import Booking, BookingSegment, InventoryHold, Offer
from .state import transition

logger = logging.getLogger("wayfare.booking")

#: Only a ticketed journey can be exchanged. Before that it is cheaper to cancel and rebook.
CHANGEABLE = frozenset({BookingStatus.TICKETED, BookingStatus.CONFIRMED})


@dataclass(frozen=True, slots=True)
class ChangeQuote:
    currency: str
    old_total: Money
    new_total: Money
    fare_difference: Money
    change_fee: Money
    #: What the traveller pays now. Never negative unless the family allows residual value.
    amount_due: Money
    residual: Money
    changeable: bool
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "old_total": self.old_total.as_dict(),
            "new_total": self.new_total.as_dict(),
            "fare_difference": self.fare_difference.as_dict(),
            "change_fee": self.change_fee.as_dict(),
            "amount_due": self.amount_due.as_dict(),
            "residual": self.residual.as_dict(),
            "changeable": self.changeable,
            "reason": self.reason,
        }


def quote_change(booking: Booking, offer: Offer) -> ChangeQuote:
    """Price an exchange without touching anything.

    ``new fare - old fare + change fee``, floored at zero unless the fare family allows
    residual value, in which case the difference is returned as credit rather than cash.
    """
    currency = booking.currency
    if offer.currency != currency:
        raise FareRuleViolation("An exchange must stay in the currency the booking was sold in.")

    family = _fare_family(booking)
    changeable = bool(family and family.changeable)
    change_fee = Money(Decimal(family.change_fee), currency) if family else Money.zero(currency)

    old_total = Money(Decimal(booking.total_amount), currency)
    new_total = Money(Decimal(offer.total_amount), currency)
    difference = new_total - old_total

    gross = difference + change_fee
    residual = Money.zero(currency)
    amount_due = gross

    if gross.amount < 0:
        if family and family.allows_residual_value:
            residual = -gross
        amount_due = Money.zero(currency)

    return ChangeQuote(
        currency=currency,
        old_total=old_total,
        new_total=new_total,
        fare_difference=difference,
        change_fee=change_fee,
        amount_due=amount_due,
        residual=residual,
        changeable=changeable,
        reason=(
            f"{family.name} may be changed for a {change_fee} fee."
            if changeable
            else "This fare family does not permit changes."
        ),
    )


@transaction.atomic
def confirm_change(booking: Booking, offer: Offer, *, actor=None) -> tuple[Booking, ChangeQuote]:
    """Move a ticketed booking onto a new itinerary.

    The new seats are taken before the old ones go back — losing the old inventory and then
    failing to get the new would leave the passenger with no flight at all.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)

    if booking.status not in CHANGEABLE:
        raise InvalidTransition(f"A {booking.status} booking cannot be changed.")

    quote = quote_change(booking, offer)
    if not quote.changeable:
        raise FareRuleViolation(quote.reason)

    segments = offer.itinerary.get("segments", [])
    if not segments:
        raise FareRuleViolation("That offer has no flights on it.")

    seats = booking.passengers.exclude(type="INF").count() or 1
    old_segments = list(booking.segments.all())
    old_total = Decimal(booking.total_amount)

    new_requests = [
        SeatRequest(
            flight_id=segment["flight_id"],
            cabin=segment["cabin"],
            rbd=segment["rbd"],
            seats=seats,
        )
        for segment in segments
    ]
    # The old seats stay sold until the exchange is paid for. A passenger who abandons the
    # change keeps the flight they already hold a ticket for.
    hold(new_requests)

    _add_segments(booking, offer, segments, after=len(old_segments))
    expires_at = _record_holds(booking, offer, new_requests)

    booking.hold_expires_at = expires_at
    booking.total_amount = Decimal(offer.total_amount) + quote.change_fee.amount
    booking.base_amount = _amount(offer.price_breakdown, "base")
    booking.tax_amount = _amount(offer.price_breakdown, "taxes")
    booking.fee_amount = _amount(offer.price_breakdown, "fees") + quote.change_fee.amount
    booking.price_breakdown = offer.price_breakdown
    booking.save(
        update_fields=[
            "total_amount", "base_amount", "tax_amount", "fee_amount",
            "price_breakdown", "hold_expires_at", "updated_at",
        ]
    )

    from apps.payments.services.ledger import post_reprice

    post_reprice(booking, booking.total_amount - old_total, reference=f"change:{booking.pnr}")

    transition(booking, BookingStatus.CHANGE_PENDING, actor=actor, reason="exchange requested")

    emit(
        "booking",
        booking.pnr,
        "booking_change_requested",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "amount_due": quote.amount_due.as_dict(),
            "segments": [s["designator"] for s in segments],
        },
    )

    logger.info(
        "change_confirmed",
        extra={"pnr": booking.pnr, "due": str(quote.amount_due.amount)},
    )

    # Nothing more to collect: the exchange completes now rather than waiting on a payment
    # that would be for zero.
    if quote.amount_due.amount <= 0:
        from apps.ticketing.services.exchange import exchange_tickets

        exchange_tickets(booking, actor=actor)
        booking.refresh_from_db()

    return booking, quote


def _add_segments(
    booking: Booking, offer: Offer, segments: list[dict], *, after: int
) -> None:
    """Add the proposed segments alongside the current ones.

    They sit at `HELD` until the exchange is ticketed; the old ones stay `CONFIRMED` so the
    passenger still has a flight if the change is never paid for. Old segments are never
    deleted — their coupons reference them.
    """
    flights = {
        flight.id: flight
        for flight in Flight.objects.filter(id__in=[s["flight_id"] for s in segments])
    }

    BookingSegment.objects.bulk_create(
        [
            BookingSegment(
                booking=booking,
                flight_id=segment["flight_id"],
                sequence=after + index,
                cabin=segment["cabin"],
                rbd=segment["rbd"],
                fare_family=offer.fare_family,
                marketing_flight_number=segment["designator"],
                status=SegmentStatus.HELD,
            )
            for index, segment in enumerate(segments)
            if segment["flight_id"] in flights
        ]
    )


def _record_holds(booking: Booking, offer: Offer, requests: list[SeatRequest]):
    from datetime import timedelta

    from django.conf import settings

    expires_at = timezone.now() + timedelta(minutes=settings.HOLD_TTL_MINUTES)
    InventoryHold.objects.bulk_create(
        [
            InventoryHold(
                booking=booking,
                offer_id=offer.offer_id,
                flight_id=request.flight_id,
                cabin=request.cabin,
                rbd=request.rbd,
                seats=request.seats,
                expires_at=expires_at,
                hold_key=f"{booking.pnr}:change:{request.flight_id}",
            )
            for request in requests
        ]
    )
    return expires_at


def _fare_family(booking: Booking):
    """The family being changed *out of* — its rules set the fee, not the new fare's."""
    segment = (
        booking.segments.select_related("fare_family")
        .filter(status=SegmentStatus.CONFIRMED)
        .first()
    ) or booking.segments.select_related("fare_family").first()
    return segment.fare_family if segment else None


def _amount(breakdown: dict, key: str) -> Decimal:
    return Decimal(str(breakdown.get(key, {}).get("amount", "0")))


@transaction.atomic
def abandon_change(booking: Booking) -> None:
    """Undo an exchange nobody paid for, leaving the original journey intact.

    The proposed seats go back and the proposed segments are dropped; the old segments were
    never touched, so the booking simply returns to the ticket it already had.
    """
    holds = list(booking.holds.filter(released_at__isnull=True))
    if holds:
        release(
            [
                SeatRequest(
                    flight_id=hold.flight_id, cabin=hold.cabin, rbd=hold.rbd, seats=hold.seats
                )
                for hold in holds
            ]
        )
        booking.holds.filter(id__in=[hold.id for hold in holds]).update(
            released_at=timezone.now()
        )

    booking.segments.filter(status=SegmentStatus.HELD).delete()

    ticket = booking.tickets.filter(status="ISSUED").first()
    if ticket is not None:
        booking.total_amount = ticket.total_amount
    booking.hold_expires_at = None
    booking.save(update_fields=["total_amount", "hold_expires_at", "updated_at"])

    transition(booking, BookingStatus.TICKETED, reason="change abandoned")
    logger.info("change_abandoned", extra={"pnr": booking.pnr})
