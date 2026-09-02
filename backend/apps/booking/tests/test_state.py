import pytest

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.booking.services.state import can_transition, transition
from apps.common.exceptions import InvalidTransition
from apps.ops.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def booking(db):
    return Booking.objects.create(
        pnr="TEST01", status=BookingStatus.DRAFT, contact_email="t@example.com"
    )


def test_a_legal_move_updates_status_and_bumps_version(booking):
    transition(booking, BookingStatus.HELD)

    assert booking.status == BookingStatus.HELD
    assert booking.version == 2


def test_an_illegal_move_raises_and_changes_nothing(booking):
    with pytest.raises(InvalidTransition):
        transition(booking, BookingStatus.TICKETED)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DRAFT
    assert booking.version == 1


def test_every_transition_is_audited(booking):
    transition(booking, BookingStatus.HELD, reason="offer accepted")

    entry = AuditLog.objects.get(object_id="TEST01")
    assert entry.action == "booking.held"
    assert entry.before["status"] == BookingStatus.DRAFT
    assert entry.after["status"] == BookingStatus.HELD
    assert entry.reason == "offer accepted"


def test_cancelling_stamps_the_time_and_reason(booking):
    transition(booking, BookingStatus.HELD)
    transition(booking, BookingStatus.CANCELLED, reason="customer changed plans")

    assert booking.cancelled_at is not None
    assert booking.cancellation_reason == "customer changed plans"


def test_terminal_states_go_nowhere(booking):
    assert not can_transition(BookingStatus.EXPIRED, BookingStatus.HELD)
    assert not can_transition(BookingStatus.REFUNDED, BookingStatus.CONFIRMED)


def test_a_booking_that_moved_under_us_loses_the_race(booking):
    """Two workers, one hold: the second must not overwrite the first's decision."""
    Booking.objects.filter(pk=booking.pk).update(status=BookingStatus.HELD)

    with pytest.raises(InvalidTransition):
        transition(booking, BookingStatus.HELD)
