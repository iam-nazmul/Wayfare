import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.booking.constants import BookingStatus, SegmentStatus
from apps.booking.models import Booking
from apps.booking.services.state import transition
from apps.common.exceptions import InvalidTransition
from apps.ops.services.outbox import emit

from ..constants import CouponStatus, TicketEventType, TicketStatus
from ..models import Ticket, TicketCoupon, TicketEvent
from .numbers import next_ticket_number

logger = logging.getLogger("wayfare.ticketing")


@transaction.atomic
def exchange_tickets(
    booking: Booking,
    *,
    actor=None,
    from_status: str = BookingStatus.CHANGE_PENDING,
) -> list[Ticket]:
    """Reissue a booking's tickets onto its new segments.

    The old coupons go to `EXCHANGED` — not `REFUNDED`, because their value moved into the new
    ticket rather than back to the passenger — and each new ticket points at the one it
    replaces through ``conjunction_of``, which is how the two are reconciled later.

    ``from_status`` is the state the reissue is expected to start from: `CHANGE_PENDING` for a
    passenger-initiated exchange, `REBOOKED` for a carrier-caused rebooking. Both land on
    `TICKETED`.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)

    if booking.status != from_status:
        raise InvalidTransition(f"A {booking.status} booking is not awaiting an exchange.")

    segments = list(
        booking.segments.filter(status=SegmentStatus.HELD)
        .select_related("flight__airline")
        .order_by("sequence")
    )
    if not segments:
        raise InvalidTransition("There are no new segments to reissue onto.")

    _swap_inventory(booking, segments)

    old_tickets = {
        ticket.passenger_id: ticket
        for ticket in booking.tickets.filter(status=TicketStatus.ISSUED)
    }
    airline = segments[0].flight.airline
    issued_at = timezone.now()
    passengers = list(booking.passengers.all())
    shares = _split(booking, passengers)

    reissued: list[Ticket] = []
    for passenger in passengers:
        previous = old_tickets.get(passenger.id)
        if previous is not None:
            _close_out(previous, booking)

        fare, tax = shares[passenger.id]
        ticket = Ticket.objects.create(
            ticket_number=next_ticket_number(airline.ticketing_prefix),
            booking=booking,
            passenger=passenger,
            issuing_airline=airline,
            issued_at=issued_at,
            issued_by=actor if actor is not None and actor.is_authenticated else None,
            status=TicketStatus.ISSUED,
            fare_amount=fare,
            tax_amount=tax,
            total_amount=fare + tax,
            currency=booking.currency,
            fare_calculation=_fare_calculation(segments),
            conjunction_of=previous,
        )
        TicketCoupon.objects.bulk_create(
            [
                TicketCoupon(ticket=ticket, segment=segment, coupon_number=index)
                for index, segment in enumerate(segments, start=1)
            ]
        )
        TicketEvent.objects.create(
            ticket=ticket,
            event_type=TicketEventType.ISSUED,
            actor=ticket.issued_by,
            payload={
                "pnr": booking.pnr,
                "coupons": len(segments),
                "reissue_of": previous.ticket_number if previous else None,
            },
        )
        reissued.append(ticket)

    booking.segments.filter(id__in=[s.id for s in segments]).update(
        status=SegmentStatus.CONFIRMED
    )
    Booking.objects.filter(pk=booking.pk).update(hold_expires_at=None)
    transition(booking, BookingStatus.TICKETED, actor=actor, reason="exchange ticketed")

    emit(
        "booking",
        booking.pnr,
        "booking_exchanged",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "tickets": [ticket.ticket_number for ticket in reissued],
        },
    )

    logger.info(
        "tickets_exchanged", extra={"pnr": booking.pnr, "count": len(reissued)}
    )
    return reissued


def _swap_inventory(booking: Booking, new_segments: list) -> None:
    """Settle the new seats and give the old ones back, in that order.

    Releasing first would leave a window where the passenger holds neither. The new holds may
    already be sold if a delta was paid, in which case settling them is a no-op.
    """
    from apps.inventory.services.availability import SeatRequest, confirm, unsell

    new_ids = {segment.id for segment in new_segments}
    seats = booking.passengers.exclude(type="INF").count() or 1

    holds = list(booking.holds.filter(released_at__isnull=True))
    if holds:
        confirm(
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

    superseded = list(
        booking.segments.filter(status=SegmentStatus.CONFIRMED).exclude(id__in=new_ids)
    )
    if superseded:
        unsell(
            [
                SeatRequest(
                    flight_id=segment.flight_id,
                    cabin=segment.cabin,
                    rbd=segment.rbd,
                    seats=seats,
                )
                for segment in superseded
            ]
        )
        booking.segments.filter(id__in=[s.id for s in superseded]).update(
            status=SegmentStatus.CANCELLED
        )


def _close_out(ticket: Ticket, booking: Booking) -> None:
    ticket.coupons.filter(status=CouponStatus.OPEN).update(status=CouponStatus.EXCHANGED)
    Ticket.objects.filter(pk=ticket.pk).update(status=TicketStatus.EXCHANGED)
    TicketEvent.objects.create(
        ticket=ticket,
        event_type=TicketEventType.EXCHANGED,
        payload={"pnr": booking.pnr},
    )


def _split(booking: Booking, passengers: list) -> dict[int, tuple[Decimal, Decimal]]:
    """See ``issue._split``; the remainder lands on the first seated passenger."""
    from .issue import _split as split_totals

    return split_totals(booking, passengers)


def _fare_calculation(segments: list) -> str:
    from .issue import _fare_calculation as build

    return build(segments)
