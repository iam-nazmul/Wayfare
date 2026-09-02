from types import MappingProxyType

from django.db.models import F
from django.utils import timezone

from apps.common.exceptions import InvalidTransition
from apps.ops.services.audit import record

from ..constants import BookingStatus
from ..models import Booking

#: The whole legal state machine, in one place (SPEC.md §5.5). Anything not listed is a bug in
#: the caller, not a state worth adding on the fly.
TRANSITIONS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        BookingStatus.DRAFT: frozenset({BookingStatus.HELD, BookingStatus.EXPIRED}),
        BookingStatus.HELD: frozenset(
            {
                BookingStatus.PENDING_TICKETING,
                BookingStatus.EXPIRED,
                BookingStatus.CANCELLED,
            }
        ),
        BookingStatus.PENDING_TICKETING: frozenset(
            {BookingStatus.TICKETED, BookingStatus.CANCELLED}
        ),
        BookingStatus.TICKETED: frozenset(
            {
                BookingStatus.CONFIRMED,
                BookingStatus.CHANGE_PENDING,
                BookingStatus.DISRUPTED,
                BookingStatus.CANCELLED,
            }
        ),
        BookingStatus.CONFIRMED: frozenset(
            {
                BookingStatus.CHANGE_PENDING,
                BookingStatus.DISRUPTED,
                BookingStatus.CANCELLED,
            }
        ),
        BookingStatus.CHANGE_PENDING: frozenset(
            {BookingStatus.TICKETED, BookingStatus.CANCELLED}
        ),
        BookingStatus.DISRUPTED: frozenset(
            {BookingStatus.REBOOKED, BookingStatus.REFUND_PENDING, BookingStatus.CANCELLED}
        ),
        BookingStatus.REBOOKED: frozenset({BookingStatus.TICKETED, BookingStatus.CANCELLED}),
        BookingStatus.CANCELLED: frozenset({BookingStatus.REFUND_PENDING}),
        BookingStatus.REFUND_PENDING: frozenset({BookingStatus.REFUNDED}),
        BookingStatus.REFUNDED: frozenset(),
        BookingStatus.EXPIRED: frozenset(),
    }
)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, frozenset())


def transition(
    booking: Booking, to_status: str, *, actor=None, reason: str = ""
) -> Booking:
    """The only way a booking changes status.

    Bumps ``version`` in the same statement so a concurrent ``If-Match`` writer loses cleanly,
    and writes the audit row that says who moved it and why.
    """
    from_status = booking.status

    if not can_transition(from_status, to_status):
        raise InvalidTransition(
            f"A booking cannot go from {from_status} to {to_status}."
        )

    fields = {"status": to_status, "version": F("version") + 1}

    if to_status == BookingStatus.CANCELLED:
        fields["cancelled_at"] = timezone.now()
        if reason:
            fields["cancellation_reason"] = reason

    # Guarded on the status we read: if another worker moved the booking first, we lose the
    # race here rather than overwriting its decision.
    if Booking.objects.filter(pk=booking.pk, status=from_status).update(**fields) == 0:
        booking.refresh_from_db()
        raise InvalidTransition(
            f"A booking cannot go from {booking.status} to {to_status}."
        )

    booking.refresh_from_db()

    record(
        f"booking.{to_status.lower()}",
        "booking",
        booking.pnr,
        actor=actor,
        before={"status": from_status},
        after={"status": to_status},
        reason=reason,
    )
    return booking
