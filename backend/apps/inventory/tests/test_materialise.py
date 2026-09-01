from datetime import date, time, timedelta

import pytest

from apps.inventory.models import BookingClass, CabinConfig, Flight, FlightSchedule, Route, Seat
from apps.inventory.services.materialise import materialise_schedule

pytestmark = pytest.mark.django_db


def make_schedule(airline, airports, aircraft, seat_map, **overrides):
    route = Route.objects.create(
        airline=airline,
        origin_airport=airports[overrides.pop("origin", "DAC")],
        destination_airport=airports[overrides.pop("destination", "DXB")],
    )
    defaults = {
        "airline": airline,
        "flight_number": "101",
        "route": route,
        "aircraft": aircraft,
        "seat_map_template": seat_map,
        "dep_time_local": time(2, 30),
        "arr_time_local": time(5, 45),
        "arrival_day_offset": 0,
        "days_of_week": [True] * 7,
        "effective_from": date.today(),
        "effective_to": date.today() + timedelta(days=60),
        "default_cabin_capacity": {"ECONOMY": 12},
    }
    defaults.update(overrides)
    return FlightSchedule.objects.create(**defaults)


def test_materialise_creates_flights_inventory_and_seats(
    airline, airports, aircraft, seat_map
):
    schedule = make_schedule(airline, airports, aircraft, seat_map)
    start = date.today() + timedelta(days=1)
    created, skipped = materialise_schedule(schedule, start, start + timedelta(days=2))

    assert (created, skipped) == (3, 0)
    flight = Flight.objects.order_by("departure_utc").first()
    assert CabinConfig.objects.filter(flight=flight, capacity=12).exists()
    # Nested inventory: every RBD is authorised at full cabin capacity by design.
    assert BookingClass.objects.filter(flight=flight).count() == 7
    assert Seat.objects.filter(flight=flight).count() == 18  # rows 10-12 x 6 columns


def test_local_wall_clock_is_preserved_and_utc_is_offset(
    airline, airports, aircraft, seat_map
):
    """DAC is UTC+6, so an 02:30 local departure is 20:30 UTC the previous day."""
    schedule = make_schedule(airline, airports, aircraft, seat_map)
    start = date.today() + timedelta(days=1)
    materialise_schedule(schedule, start, start)

    flight = Flight.objects.get()
    assert (flight.departure_local.hour, flight.departure_local.minute) == (2, 30)
    assert (flight.departure_utc.hour, flight.departure_utc.minute) == (20, 30)
    assert flight.departure_utc.date() == flight.departure_local.date() - timedelta(days=1)


def test_overnight_flight_needs_the_day_offset(airline, airports, aircraft, seat_map):
    """Without arrival_day_offset the arrival precedes departure, so the date is skipped."""
    schedule = make_schedule(
        airline, airports, aircraft, seat_map,
        dep_time_local=time(23, 30), arr_time_local=time(6, 30), arrival_day_offset=0,
    )
    start = date.today() + timedelta(days=1)
    created, skipped = materialise_schedule(schedule, start, start)

    assert (created, skipped) == (0, 1)
    assert not Flight.objects.exists()


def test_overnight_flight_with_day_offset_is_created(airline, airports, aircraft, seat_map):
    schedule = make_schedule(
        airline, airports, aircraft, seat_map,
        dep_time_local=time(23, 30), arr_time_local=time(6, 30), arrival_day_offset=1,
    )
    start = date.today() + timedelta(days=1)
    created, _ = materialise_schedule(schedule, start, start)

    assert created == 1
    assert Flight.objects.get().duration_minutes > 0


def test_rerunning_materialisation_skips_existing_dates(
    airline, airports, aircraft, seat_map
):
    schedule = make_schedule(airline, airports, aircraft, seat_map)
    start = date.today() + timedelta(days=1)

    first_created, _ = materialise_schedule(schedule, start, start + timedelta(days=1))
    second_created, second_skipped = materialise_schedule(schedule, start, start + timedelta(days=1))

    assert first_created == 2
    assert (second_created, second_skipped) == (0, 2)
    assert Flight.objects.count() == 2


def test_days_of_week_filter_is_respected(airline, airports, aircraft, seat_map):
    monday_only = [True, False, False, False, False, False, False]
    schedule = make_schedule(airline, airports, aircraft, seat_map, days_of_week=monday_only)
    start = date.today() + timedelta(days=1)

    created, _ = materialise_schedule(schedule, start, start + timedelta(days=13))

    assert created == 2  # exactly two Mondays in a fortnight
    assert all(f.departure_local.weekday() == 0 for f in Flight.objects.all())
