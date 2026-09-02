"""A signed-in traveller sees their own bookings and nobody else's."""

import uuid

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.booking.models import Booking

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def _book(client, flight, *, last_name="Islam") -> str:
    offer_id = client.post(
        reverse("v1:search-flights"),
        {
            "trip_type": "ONE_WAY",
            "slices": [
                {
                    "origin": "DAC",
                    "destination": "DXB",
                    "date": flight.departure_local.date().isoformat(),
                }
            ],
            "passengers": {"adults": 1, "children": 0, "infants": 0},
            "cabin": "ECONOMY",
            "currency": "USD",
            "max_stops": 0,
        },
        format="json",
    ).data["slices"][0]["offers"][0]["offer_id"]

    return client.post(
        reverse("v1:booking-create"),
        {
            "offer_id": offer_id,
            "passengers": [
                {"type": "ADT", "first_name": "Nazmul", "last_name": last_name,
                 "dob": "1990-05-14"}
            ],
            "contact": {"email": "traveller@example.com"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data["pnr"]


def test_signing_in_is_required(client):
    assert client.get(reverse("v1:my-bookings")).status_code in (401, 403)


def test_a_traveller_sees_the_booking_they_made(client, make_flight, make_fare, traveller):
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client.force_authenticate(traveller)
    pnr = _book(client, flight)

    response = client.get(reverse("v1:my-bookings"))

    assert response.status_code == 200
    assert [row["pnr"] for row in response.data["results"]] == [pnr]

    row = response.data["results"][0]
    assert (row["origin"], row["destination"]) == ("DAC", "DXB")
    assert row["passenger_count"] == 1
    assert row["total"] == {"amount": "200.00", "currency": "USD"}


def test_another_traveller_sees_nothing_of_it(client, make_flight, make_fare, traveller):
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client.force_authenticate(traveller)
    _book(client, flight)

    intruder = User.objects.create_user(email="other@test.local", password="test-pass-12345")
    client.force_authenticate(intruder)

    assert client.get(reverse("v1:my-bookings")).data["results"] == []


def test_a_guest_booking_belongs_to_nobody(client, make_flight, make_fare, traveller):
    """Booked signed-out, so it is retrievable by PNR + surname and not by account."""
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    pnr = _book(client, flight)
    assert Booking.objects.get(pnr=pnr).user is None

    client.force_authenticate(traveller)
    assert client.get(reverse("v1:my-bookings")).data["results"] == []


def test_the_newest_booking_comes_first(client, make_flight, make_fare, traveller):
    make_fare(rbd="Y", amount="200.00")
    client.force_authenticate(traveller)

    first = _book(client, make_flight(days_ahead=20, capacity=10, rbd="Y"))
    second = _book(
        client, make_flight(days_ahead=25, capacity=10, rbd="Y", flight_number="102")
    )

    rows = client.get(reverse("v1:my-bookings")).data["results"]
    assert [row["pnr"] for row in rows] == [second, first]


def test_the_list_is_paginated(client, make_flight, make_fare, traveller):
    make_fare(rbd="Y", amount="200.00")
    client.force_authenticate(traveller)
    _book(client, make_flight(days_ahead=20, capacity=10, rbd="Y"))

    body = client.get(reverse("v1:my-bookings")).data
    assert {"results", "next", "previous"} <= set(body)
