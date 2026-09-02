from django.db.models import QuerySet

from apps.booking.selectors import booking_for, guest_booking

from .constants import RebookOptionStatus
from .models import Disruption, RebookOption


def booking_or_none(actor, pnr: str, last_name: str = ""):
    """Rebooking is addressed through the booking, so ownership is decided there."""
    return booking_for(actor, pnr) or guest_booking(pnr, last_name)


def rebook_options_for(booking) -> QuerySet[RebookOption]:
    """Live options only — an expired or superseded one is not something to offer again."""
    return (
        RebookOption.objects.filter(booking=booking, status=RebookOptionStatus.OFFERED)
        .select_related("proposed_flight", "disruption__flight")
        .order_by("rank")
    )


def option_for(booking, public_id) -> RebookOption | None:
    return (
        RebookOption.objects.filter(booking=booking, public_id=public_id)
        .select_related("proposed_flight", "disruption__flight")
        .first()
    )


def open_disruptions() -> QuerySet[Disruption]:
    return (
        Disruption.objects.filter(resolved_at__isnull=True)
        .select_related("flight")
        .order_by("-detected_at")
    )
