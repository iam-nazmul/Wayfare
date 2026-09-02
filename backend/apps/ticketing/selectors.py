from django.db.models import QuerySet

from apps.booking.selectors import booking_for, guest_booking

from .models import Ticket


def tickets_base() -> QuerySet[Ticket]:
    return Ticket.objects.select_related("passenger", "issuing_airline").prefetch_related(
        "coupons__segment__flight"
    )


def tickets_for(actor, pnr: str, last_name: str = "") -> QuerySet[Ticket]:
    """Tickets belong to a booking, so the booking's ownership rule decides access."""
    booking = booking_for(actor, pnr) or guest_booking(pnr, last_name)
    if booking is None:
        return tickets_base().none()

    return tickets_base().filter(booking=booking).order_by("ticket_number")
