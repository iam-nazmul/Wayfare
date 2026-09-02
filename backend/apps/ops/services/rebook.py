import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.booking.constants import BookingStatus, SegmentStatus
from apps.booking.models import Booking, BookingSegment, InventoryHold
from apps.booking.services.state import transition
from apps.common.exceptions import InvalidTransition, InventoryUnavailable
from apps.inventory.constants import SELLABLE_FLIGHT_STATUSES
from apps.inventory.services.availability import SeatRequest, hold

from ..constants import RebookOptionStatus
from ..models import RebookOption
from .outbox import emit

logger = logging.getLogger("wayfare.ops")

#: Only a disrupted booking is rebooked this way. Everything else is an ordinary exchange, which
#: charges a fare difference.
REBOOKABLE = frozenset({BookingStatus.DISRUPTED})

#: The new seats are held only long enough to reissue against them, which happens inline.
REBOOK_HOLD_MINUTES = 30


@transaction.atomic
def accept_rebooking(booking: Booking, option: RebookOption, *, actor=None) -> Booking:
    """Move a disrupted booking onto the alternative the passenger chose.

    The option holds nothing, so availability is re-read under lock here — by the time someone
    opens their email, the flight they were offered may be full. The fare difference stays
    waived: the carrier caused this.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)

    if booking.status not in REBOOKABLE:
        raise InvalidTransition(f"A {booking.status} booking is not awaiting a rebooking.")
    if option.status != RebookOptionStatus.OFFERED:
        raise InvalidTransition("That option is no longer on offer.")
    if option.expires_at <= timezone.now():
        raise InvalidTransition("That option has expired. Ask for fresh alternatives.")

    flight = option.proposed_flight
    if flight.status not in SELLABLE_FLIGHT_STATUSES:
        raise InventoryUnavailable("That flight is no longer sellable.")

    seats = booking.passengers.exclude(type="INF").count() or 1
    hold([SeatRequest(flight_id=flight.id, cabin=option.cabin, rbd=option.rbd, seats=seats)])

    disrupted = booking.segments.filter(
        flight=option.disruption.flight,
        status__in=[SegmentStatus.HELD, SegmentStatus.CONFIRMED],
    ).first()

    BookingSegment.objects.create(
        booking=booking,
        flight=flight,
        sequence=booking.segments.count(),
        cabin=option.cabin,
        rbd=option.rbd,
        fare_family=disrupted.fare_family if disrupted else None,
        marketing_flight_number=flight.designator,
        status=SegmentStatus.HELD,
    )
    InventoryHold.objects.create(
        booking=booking,
        offer_id=option.public_id,
        flight=flight,
        cabin=option.cabin,
        rbd=option.rbd,
        seats=seats,
        expires_at=timezone.now() + timedelta(minutes=REBOOK_HOLD_MINUTES),
        hold_key=f"{booking.pnr}:rebook:{flight.id}",
    )

    RebookOption.objects.filter(pk=option.pk).update(status=RebookOptionStatus.ACCEPTED)
    booking.rebook_options.filter(status=RebookOptionStatus.OFFERED).update(
        status=RebookOptionStatus.DECLINED
    )

    transition(booking, BookingStatus.REBOOKED, actor=actor, reason="rebooked after disruption")

    emit(
        "booking",
        booking.pnr,
        "booking_rebooked",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "from_flight": option.disruption.flight.designator,
            "to_flight": flight.designator,
            "departure_local": flight.departure_local.isoformat(),
        },
    )

    # Reissue inline: nothing is owed, so there is no payment to wait for. Only a ticketed
    # booking can reach DISRUPTED, so there is always a ticket to reissue.
    from apps.ticketing.services.exchange import exchange_tickets

    exchange_tickets(booking, actor=actor, from_status=BookingStatus.REBOOKED)
    booking.refresh_from_db()

    logger.info(
        "booking_rebooked",
        extra={"pnr": booking.pnr, "flight": flight.id, "option": str(option.public_id)},
    )
    return booking
