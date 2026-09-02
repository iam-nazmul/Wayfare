"""One PNR per journey, not per leg — a round trip books both slices together."""

import uuid
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.inventory.models import BookingClass, CabinConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def round_trip(client, make_flight, make_fare):
    """Two dated flights and the fares to price them, out and back."""
    outbound = make_flight(days_ahead=20, capacity=10, rbd="Y", flight_number="101")
    inbound = make_flight(
        origin="DXB", destination="DAC", days_ahead=27, capacity=10, rbd="Y",
        flight_number="102",
    )
    make_fare(rbd="Y", amount="200.00")
    make_fare(origin="DXB", destination="DAC", rbd="Y", amount="180.00")

    response = client.post(
        reverse("v1:search-flights"),
        {
            "trip_type": "ROUND_TRIP",
            "slices": [
                {
                    "origin": "DAC",
                    "destination": "DXB",
                    "date": outbound.departure_local.date().isoformat(),
                },
                {
                    "origin": "DXB",
                    "destination": "DAC",
                    "date": inbound.departure_local.date().isoformat(),
                },
            ],
            "passengers": {"adults": 1, "children": 0, "infants": 0},
            "cabin": "ECONOMY",
            "currency": "USD",
            "max_stops": 0,
        },
        format="json",
    )

    slices = response.data["slices"]
    assert len(slices) == 2, "the search must answer with a slice per leg"
    return {
        "outbound": outbound,
        "inbound": inbound,
        "offer_ids": [slices[0]["offers"][0]["offer_id"], slices[1]["offers"][0]["offer_id"]],
        "totals": [
            Decimal(slices[0]["offers"][0]["total"]["amount"]),
            Decimal(slices[1]["offers"][0]["total"]["amount"]),
        ],
    }


def book(client, offer_ids, **overrides):
    body = {
        "offer_ids": [str(offer_id) for offer_id in offer_ids],
        "passengers": [
            {"type": "ADT", "first_name": "Nazmul", "last_name": "Islam", "dob": "1990-05-14"}
        ],
        "contact": {"email": "traveller@example.com"},
    }
    body.update(overrides)
    return client.post(
        reverse("v1:booking-create"),
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


def test_both_legs_land_in_one_pnr(client, round_trip):
    response = book(client, round_trip["offer_ids"])

    assert response.status_code == 201, response.data
    assert len(response.data["segments"]) == 2

    designators = [segment["designator"] for segment in response.data["segments"]]
    assert designators == ["WF101", "WF102"]
    assert Booking.objects.count() == 1


def test_the_total_is_the_sum_of_both_slices(client, round_trip):
    """The traveller pays the sum of the two prices they were quoted, not a fresh calculation."""
    response = book(client, round_trip["offer_ids"])

    booking = Booking.objects.get(pnr=response.data["pnr"])
    assert booking.base_amount == Decimal("380.00")  # 200.00 out + 180.00 back
    assert booking.total_amount == sum(round_trip["totals"])
    assert booking.total_amount == Decimal(response.data["total"]["amount"])


def test_seats_are_held_on_both_flights(client, round_trip):
    book(client, round_trip["offer_ids"])

    for flight in (round_trip["outbound"], round_trip["inbound"]):
        assert CabinConfig.objects.get(flight=flight).seats_held == 1
        assert BookingClass.objects.get(flight=flight, rbd="Y").held == 1


def test_the_tax_lines_of_both_slices_are_kept(client, round_trip):
    """A refund has to know which taxes were refundable — on every leg, not just the first."""
    response = book(client, round_trip["offer_ids"])
    booking = Booking.objects.get(pnr=response.data["pnr"])

    assert len(booking.price_breakdown["segments"]) == 2


def test_a_one_way_booking_still_takes_a_single_offer_id(client, round_trip):
    response = client.post(
        reverse("v1:booking-create"),
        {
            "offer_id": str(round_trip["offer_ids"][0]),
            "passengers": [
                {"type": "ADT", "first_name": "Nazmul", "last_name": "Islam",
                 "dob": "1990-05-14"}
            ],
            "contact": {"email": "traveller@example.com"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 201
    assert len(response.data["segments"]) == 1


def test_sending_both_forms_is_rejected(client, round_trip):
    response = book(
        client, round_trip["offer_ids"], offer_id=str(round_trip["offer_ids"][0])
    )

    assert response.status_code == 422
    assert response.data["code"] == "validation_error"


def test_sending_no_offer_is_rejected(client):
    response = client.post(
        reverse("v1:booking-create"),
        {
            "passengers": [
                {"type": "ADT", "first_name": "A", "last_name": "B", "dob": "1990-05-14"}
            ],
            "contact": {"email": "t@example.com"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 422


def test_the_same_offer_cannot_fill_both_slices(client, round_trip):
    first = round_trip["offer_ids"][0]
    response = book(client, [first, first])

    assert response.status_code == 422
    assert not Booking.objects.exists()


def test_a_sold_out_return_leg_holds_no_outbound_seat(client, round_trip):
    """Both legs are held in one transaction: losing the return must not keep the outbound."""
    CabinConfig.objects.filter(flight=round_trip["inbound"]).update(seats_sold=10)
    BookingClass.objects.filter(flight=round_trip["inbound"]).update(sold=10)

    response = book(client, round_trip["offer_ids"])

    assert response.status_code == 409
    assert response.data["code"] == "inventory_unavailable"
    assert CabinConfig.objects.get(flight=round_trip["outbound"]).seats_held == 0
    assert not Booking.objects.exists()


def test_a_round_trip_pays_and_tickets_as_one(client, round_trip, celery_eager):
    pnr = book(client, round_trip["offer_ids"]).data["pnr"]

    intent = client.post(
        reverse("v1:payment-intent-create", args=[pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data
    client.post(
        reverse("v1:payment-intent-confirm", args=[pnr, intent["intent_id"]]),
        {"card_number": "4242424242424242", "last_name": "Islam"},
        format="json",
    )

    booking = Booking.objects.get(pnr=pnr)
    assert booking.status == BookingStatus.TICKETED

    # One ticket for the passenger, with a coupon per flown segment.
    from apps.ticketing.models import Ticket

    ticket = Ticket.objects.get()
    assert ticket.coupons.count() == 2
