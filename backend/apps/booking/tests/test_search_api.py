from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def priced_flight(make_flight, make_fare):
    flight = make_flight(days_ahead=7, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")
    return flight


def payload(flight, **overrides):
    body = {
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
    }
    body.update(overrides)
    return body


def test_search_is_public_and_returns_priced_offers(client, priced_flight):
    response = client.post(
        reverse("v1:search-flights"), payload(priced_flight), format="json"
    )
    assert response.status_code == 200

    offers = response.data["slices"][0]["offers"]
    assert len(offers) == 1
    assert offers[0]["total"] == {"amount": "200.00", "currency": "USD"}
    assert offers[0]["itinerary"]["stops"] == 0


def test_money_is_serialized_as_decimal_strings(client, priced_flight):
    response = client.post(
        reverse("v1:search-flights"), payload(priced_flight), format="json"
    )
    total = response.data["slices"][0]["offers"][0]["total"]
    assert isinstance(total["amount"], str)
    assert total["amount"] == "200.00"


def test_past_date_is_rejected(client, priced_flight):
    from django.utils import timezone

    body = payload(priced_flight)
    body["slices"][0]["date"] = (timezone.now().date() - timedelta(days=1)).isoformat()

    response = client.post(reverse("v1:search-flights"), body, format="json")
    assert response.status_code == 422
    assert response.data["code"] == "validation_error"


def test_same_origin_and_destination_is_rejected(client, priced_flight):
    body = payload(priced_flight)
    body["slices"][0]["destination"] = "DAC"

    response = client.post(reverse("v1:search-flights"), body, format="json")
    assert response.status_code == 422


def test_more_infants_than_adults_is_rejected(client, priced_flight):
    body = payload(priced_flight, passengers={"adults": 1, "children": 0, "infants": 2})
    response = client.post(reverse("v1:search-flights"), body, format="json")

    assert response.status_code == 422
    assert any(error["field"].endswith("infants") for error in response.data["errors"])


def test_round_trip_requires_two_slices(client, priced_flight):
    body = payload(priced_flight, trip_type="ROUND_TRIP")
    response = client.post(reverse("v1:search-flights"), body, format="json")
    assert response.status_code == 422


def test_return_before_outbound_is_rejected(client, priced_flight):
    day = priced_flight.departure_local.date()
    body = payload(
        priced_flight,
        trip_type="ROUND_TRIP",
        slices=[
            {"origin": "DAC", "destination": "DXB", "date": day.isoformat()},
            {
                "origin": "DXB",
                "destination": "DAC",
                "date": (day - timedelta(days=1)).isoformat(),
            },
        ],
    )
    response = client.post(reverse("v1:search-flights"), body, format="json")
    assert response.status_code == 422


def test_sold_out_flight_produces_no_offers(client, priced_flight):
    from apps.inventory.models import BookingClass, CabinConfig

    CabinConfig.objects.filter(flight=priced_flight).update(seats_sold=10)
    BookingClass.objects.filter(flight=priced_flight).update(sold=10)

    response = client.post(
        reverse("v1:search-flights"), payload(priced_flight), format="json"
    )
    assert response.status_code == 200
    assert response.data["slices"][0]["offers"] == []


def test_advance_purchase_gated_bucket_falls_back_to_the_next_class(
    client, make_flight, make_fare
):
    """The cheapest bucket is unqualified this close in, so the flight sells one class up."""
    from apps.inventory.models import BookingClass, CabinConfig

    flight = make_flight(days_ahead=1, capacity=10, rbd="Y")
    BookingClass.objects.create(
        flight=flight,
        cabin_config=CabinConfig.objects.get(flight=flight),
        rbd="L",
        authorised=10,
        sort_order=6,
    )
    make_fare(rbd="Y", amount="200.00")
    make_fare(rbd="L", amount="80.00", advance_purchase_days=3)

    response = client.post(reverse("v1:search-flights"), payload(flight), format="json")
    assert response.status_code == 200

    offers = response.data["slices"][0]["offers"]
    assert len(offers) == 1
    assert offers[0]["itinerary"]["segments"][0]["rbd"] == "Y"
    assert offers[0]["total"] == {"amount": "200.00", "currency": "USD"}


def test_no_qualifying_fare_on_any_open_class_produces_no_offers(
    client, make_flight, make_fare
):
    flight = make_flight(days_ahead=2, capacity=10, rbd="L", flight_number="102")
    make_fare(rbd="L", amount="80.00", advance_purchase_days=3)

    response = client.post(reverse("v1:search-flights"), payload(flight), format="json")
    assert response.status_code == 200
    assert response.data["slices"][0]["offers"] == []


def test_airport_typeahead_is_public(client, airports):
    response = client.get(reverse("v1:airport-list"), {"q": "DAC"})
    assert response.status_code == 200
    assert response.data[0]["iata_code"] == "DAC"


def test_ops_endpoints_reject_anonymous_callers(client):
    response = client.get(reverse("v1:ops-flight-list"))
    assert response.status_code in (401, 403)


def test_ops_endpoints_reject_a_plain_traveller(client, traveller):
    client.force_authenticate(traveller)
    response = client.get(reverse("v1:ops-flight-list"))
    assert response.status_code == 403
