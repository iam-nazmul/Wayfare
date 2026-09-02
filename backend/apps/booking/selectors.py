from django.db.models import QuerySet

from apps.accounts.constants import STAFF_ROLES

from .models import Booking


def _is_staff(actor) -> bool:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if actor.is_superuser:
        return True
    return actor.role_assignments.filter(role__in=STAFF_ROLES).exists()


def bookings_base() -> QuerySet[Booking]:
    return Booking.objects.prefetch_related(
        "passengers",
        "segments__flight__origin_airport",
        "segments__flight__destination_airport",
        "segments__flight__airline",
    )


def bookings_for(actor) -> QuerySet[Booking]:
    """Every non-staff read is filtered here, never in the view (CLAUDE.md invariant 8)."""
    if _is_staff(actor):
        return bookings_base()

    if actor is None or not getattr(actor, "is_authenticated", False):
        return bookings_base().none()

    agency_ids = list(
        actor.agency_memberships.values_list("agency_id", flat=True)
    )
    if agency_ids:
        return bookings_base().filter(agency_id__in=agency_ids) | bookings_base().filter(
            user=actor
        )

    return bookings_base().filter(user=actor)


def booking_for(actor, pnr: str) -> Booking | None:
    return bookings_for(actor).filter(pnr=pnr.upper()).first()


def guest_booking(pnr: str, last_name: str) -> Booking | None:
    """Retrieval without an account: the PNR alone is not enough, a surname must match too."""
    if not pnr or not last_name:
        return None

    return (
        bookings_base()
        .filter(pnr=pnr.upper(), passengers__last_name__iexact=last_name.strip())
        .distinct()
        .first()
    )
