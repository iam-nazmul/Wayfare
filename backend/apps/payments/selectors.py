from django.db.models import QuerySet

from apps.booking.selectors import booking_for, guest_booking

from .models import Payment, PaymentIntent


def booking_or_none(actor, pnr: str, last_name: str = ""):
    """Payments are addressed through their booking, so ownership is decided there."""
    return booking_for(actor, pnr) or guest_booking(pnr, last_name)


def payments_for_booking(booking) -> QuerySet[Payment]:
    return Payment.objects.filter(booking=booking).order_by("-created_at")


def intent_for(actor, pnr: str, public_id, last_name: str = "") -> PaymentIntent | None:
    booking = booking_or_none(actor, pnr, last_name)
    if booking is None:
        return None
    return PaymentIntent.objects.filter(booking=booking, public_id=public_id).first()
