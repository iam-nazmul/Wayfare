import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.booking.services.state import transition
from apps.common.exceptions import InvalidTransition
from apps.ops.services.outbox import emit
from apps.pricing.constants import PassengerType

from ..constants import TicketEventType, TicketStatus
from ..models import Ticket, TicketCoupon, TicketEvent
from .numbers import next_ticket_number

logger = logging.getLogger("wayfare.ticketing")

ISSUABLE_STATUSES = frozenset({BookingStatus.PENDING_TICKETING})


@transaction.atomic
def issue_tickets(booking: Booking, *, actor=None) -> list[Ticket]:
    """Allocate ticket numbers and coupons for every passenger on a paid booking.

    Idempotent: a booking that already has live tickets returns them rather than issuing a
    second set. The task that calls this is `acks_late`, so it will be delivered twice.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)

    existing = list(booking.tickets.filter(status=TicketStatus.ISSUED))
    if existing:
        logger.info("tickets_already_issued", extra={"pnr": booking.pnr})
        return existing

    if booking.status not in ISSUABLE_STATUSES:
        raise InvalidTransition(f"A {booking.status} booking cannot be ticketed.")

    segments = list(booking.segments.select_related("flight__airline").order_by("sequence"))
    if not segments:
        raise InvalidTransition("There are no segments to ticket.")

    passengers = list(booking.passengers.all())
    airline = segments[0].flight.airline
    issued_at = timezone.now()
    shares = _split(booking, passengers)

    tickets = []
    for passenger in passengers:
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
            payload={"coupons": len(segments), "pnr": booking.pnr},
        )
        tickets.append(ticket)

    transition(booking, BookingStatus.TICKETED, actor=actor, reason="tickets issued")

    emit(
        "booking",
        booking.pnr,
        "ticket_issued",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "tickets": [ticket.ticket_number for ticket in tickets],
        },
    )

    logger.info(
        "tickets_issued",
        extra={"pnr": booking.pnr, "count": len(tickets), "coupons": len(segments)},
    )
    return tickets


def _split(booking: Booking, passengers: list) -> dict[int, tuple[Decimal, Decimal]]:
    """Divide the booking total across passengers, giving the remainder to the first.

    Infants pay a token fare and are not counted as a full share; the point is that the sum of
    the tickets equals the booking to the cent, because a ticket is a financial document.
    """
    seated = [p for p in passengers if p.type != PassengerType.INFANT] or passengers
    fare_each = (Decimal(booking.base_amount) / len(seated)).quantize(Decimal("0.01"))
    tax_each = (
        (Decimal(booking.tax_amount) + Decimal(booking.fee_amount)) / len(seated)
    ).quantize(Decimal("0.01"))

    shares: dict[int, tuple[Decimal, Decimal]] = {}
    fare_left = Decimal(booking.base_amount)
    tax_left = Decimal(booking.tax_amount) + Decimal(booking.fee_amount)

    for passenger in passengers:
        if passenger.type == PassengerType.INFANT and len(seated) != len(passengers):
            shares[passenger.id] = (Decimal("0.00"), Decimal("0.00"))
            continue
        shares[passenger.id] = (fare_each, tax_each)
        fare_left -= fare_each
        tax_left -= tax_each

    if fare_left or tax_left:
        first = seated[0]
        fare, tax = shares[first.id]
        shares[first.id] = (fare + fare_left, tax + tax_left)

    return shares


def _fare_calculation(segments: list) -> str:
    """The linear fare construction printed on the ticket: ORG XX DST XX DST."""
    parts = [segments[0].flight.origin_airport_id]
    for segment in segments:
        parts += [segment.flight.airline_id, segment.flight.destination_airport_id]
    return " ".join(parts)
