import threading

import pytest
from django.db import connections

from apps.common.exceptions import InventoryUnavailable
from apps.inventory.models import BookingClass, CabinConfig
from apps.inventory.services.availability import (
    SeatRequest,
    cheapest_open_class,
    confirm,
    hold,
    release,
    unsell,
)

pytestmark = pytest.mark.django_db


def test_cheapest_open_class_returns_the_open_bucket(make_flight):
    flight = make_flight(capacity=10, rbd="Q")
    result = cheapest_open_class(flight.id, "ECONOMY", 2)
    assert result is not None
    assert result.rbd == "Q"


def test_cheapest_open_class_respects_the_cabin_ceiling(make_flight):
    """An RBD authorised above cabin capacity must not sell past the cabin."""
    flight = make_flight(capacity=2, rbd="Q", authorised=50)
    assert cheapest_open_class(flight.id, "ECONOMY", 2) is not None
    assert cheapest_open_class(flight.id, "ECONOMY", 3) is None


def test_cheapest_open_class_ignores_closed_buckets(make_flight):
    flight = make_flight(capacity=10, rbd="Q")
    BookingClass.objects.filter(flight=flight).update(is_open=False)
    assert cheapest_open_class(flight.id, "ECONOMY", 1) is None


def test_hold_then_confirm_moves_held_to_sold(make_flight):
    flight = make_flight(capacity=5, rbd="Y")
    request = [SeatRequest(flight.id, "ECONOMY", "Y", 2)]

    hold(request)
    cabin = CabinConfig.objects.get(flight=flight)
    assert (cabin.seats_held, cabin.seats_sold) == (2, 0)

    confirm(request)
    cabin.refresh_from_db()
    assert (cabin.seats_held, cabin.seats_sold) == (0, 2)

    booking_class = BookingClass.objects.get(flight=flight)
    assert (booking_class.held, booking_class.sold) == (0, 2)


def test_release_returns_the_seats(make_flight):
    flight = make_flight(capacity=5, rbd="Y")
    request = [SeatRequest(flight.id, "ECONOMY", "Y", 3)]

    hold(request)
    release(request)

    cabin = CabinConfig.objects.get(flight=flight)
    assert cabin.seats_held == 0
    assert cabin.seats_available == 5


def test_unsell_reverses_a_confirmed_sale(make_flight):
    flight = make_flight(capacity=5, rbd="Y")
    request = [SeatRequest(flight.id, "ECONOMY", "Y", 1)]

    hold(request)
    confirm(request)
    unsell(request)

    cabin = CabinConfig.objects.get(flight=flight)
    assert cabin.seats_sold == 0


def test_hold_refuses_more_than_the_cabin_holds(make_flight):
    flight = make_flight(capacity=1, rbd="Y")
    with pytest.raises(InventoryUnavailable):
        hold([SeatRequest(flight.id, "ECONOMY", "Y", 2)])


def test_confirm_without_a_hold_is_refused(make_flight):
    flight = make_flight(capacity=5, rbd="Y")
    with pytest.raises(InventoryUnavailable):
        confirm([SeatRequest(flight.id, "ECONOMY", "Y", 1)])


@pytest.mark.django_db(transaction=True)
def test_last_seat_is_held_exactly_once_under_concurrency(make_flight):
    """SPEC.md §14 case 1 — the invariant the whole locking design exists for.

    transaction=True is mandatory: the default test transaction hides row-lock behaviour.
    """
    flight = make_flight(capacity=1, rbd="Y")
    request = [SeatRequest(flight.id, "ECONOMY", "Y", 1)]

    outcomes: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def attempt() -> None:
        barrier.wait()
        try:
            hold(request)
            result = "ok"
        except InventoryUnavailable:
            result = "conflict"
        finally:
            connections.close_all()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert outcomes.count("ok") == 1, outcomes
    assert outcomes.count("conflict") == 7, outcomes

    cabin = CabinConfig.objects.get(flight=flight)
    assert cabin.seats_held == 1
    assert cabin.seats_available == 0
