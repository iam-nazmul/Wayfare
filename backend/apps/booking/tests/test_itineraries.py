from datetime import date, timedelta

import pytest

from apps.booking.services.itineraries import (
    Itinerary,
    build_itineraries,
    great_circle_km,
    minimum_connect_minutes,
)

pytestmark = pytest.mark.django_db


def test_direct_flight_is_found(make_flight):
    flight = make_flight(days_ahead=7)
    day = flight.departure_local.date()

    results = build_itineraries("DAC", "DXB", day, max_stops=0)
    assert len(results) == 1
    assert results[0].stops == 0


def test_a_flight_on_another_local_date_is_not_returned(make_flight):
    """A padded UTC window would pull in the next day's operation; the local date must not."""
    flight = make_flight(days_ahead=7)
    make_flight(days_ahead=8, flight_number="101")

    results = build_itineraries("DAC", "DXB", flight.departure_local.date(), max_stops=0)
    assert len(results) == 1


def test_connection_under_mct_is_excluded(make_flight, airports):
    first = make_flight("DAC", "DXB", days_ahead=7, flight_number="101")
    # Departs 30 minutes after the inbound lands — under the 90-minute international MCT.
    second = make_flight("DXB", "LHR", days_ahead=7, flight_number="550")
    second.departure_utc = first.arrival_utc + timedelta(minutes=30)
    second.arrival_utc = second.departure_utc + timedelta(minutes=420)
    second.save()

    results = build_itineraries("DAC", "LHR", first.departure_local.date(), max_stops=1)
    assert results == []


def test_connection_above_mct_is_included(make_flight):
    first = make_flight("DAC", "DXB", days_ahead=7, flight_number="101")
    second = make_flight("DXB", "LHR", days_ahead=7, flight_number="550")
    second.departure_utc = first.arrival_utc + timedelta(minutes=150)
    second.arrival_utc = second.departure_utc + timedelta(minutes=420)
    second.save()

    results = build_itineraries("DAC", "LHR", first.departure_local.date(), max_stops=1)
    assert len(results) == 1
    assert results[0].stops == 1


def test_connection_beyond_the_window_is_excluded(make_flight):
    first = make_flight("DAC", "DXB", days_ahead=7, flight_number="101")
    second = make_flight("DXB", "LHR", days_ahead=7, flight_number="550")
    second.departure_utc = first.arrival_utc + timedelta(hours=13)
    second.arrival_utc = second.departure_utc + timedelta(minutes=420)
    second.save()

    results = build_itineraries("DAC", "LHR", first.departure_local.date(), max_stops=1)
    assert results == []


def test_minimum_connect_time_uses_the_airport_override(airports):
    airport = airports["DXB"]
    assert minimum_connect_minutes(airport, "BD", "AE") == 90  # international default
    assert minimum_connect_minutes(airport, "AE", "AE") == 45  # domestic default

    airport.mct_international_minutes = 120
    assert minimum_connect_minutes(airport, "BD", "AE") == 120


def test_great_circle_distance_is_plausible():
    dhaka_to_dubai = great_circle_km(23.843, 90.398, 25.253, 55.365)
    assert 3400 < dhaka_to_dubai < 3700


def test_great_circle_returns_zero_without_coordinates():
    assert great_circle_km(None, None, 1, 1) == 0.0


def test_itinerary_reports_stops_and_duration(make_flight):
    flight = make_flight(days_ahead=7, duration_minutes=315)
    itinerary = Itinerary((flight,))
    assert itinerary.stops == 0
    assert itinerary.total_minutes == 315
    assert itinerary.origin == "DAC"
    assert itinerary.destination == "DXB"
