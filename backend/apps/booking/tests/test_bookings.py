import uuid
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking, InventoryHold
from apps.booking.tasks import release_expired_holds
from apps.inventory.models import BookingClass, CabinConfig
from apps.ops.models import OutboxEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def offer_id(client, make_flight, make_fare):
    """A real, signed offer — booking re-validates the signature, so it cannot be faked."""
    flight = make_flight(days_ahead=30, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    response = client.post(
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
    )
    return response.data["slices"][0]["offers"][0]["offer_id"]


def adult(**overrides) -> dict:
    passenger = {
        "type": "ADT",
        "first_name": "Nazmul",
        "last_name": "Islam",
        "dob": "1990-05-14",
        "gender": "M",
        "nationality": "BD",
    }
    passenger.update(overrides)
    return passenger


def body(offer_id, **overrides) -> dict:
    payload = {
        "offer_id": str(offer_id),
        "passengers": [adult()],
        "contact": {"email": "traveller@example.com", "phone": "+8801700000000"},
    }
    payload.update(overrides)
    return payload


def create(client, offer_id, key=None, **overrides):
    return client.post(
        reverse("v1:booking-create"),
        body(offer_id, **overrides),
        format="json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def test_booking_holds_inventory_and_returns_a_pnr(client, offer_id):
    response = create(client, offer_id)

    assert response.status_code == 201
    assert response.data["status"] == BookingStatus.HELD
    assert len(response.data["pnr"]) == 6
    assert response.data["total"] == {"amount": "200.00", "currency": "USD"}
    assert response.data["hold_expires_at"] is not None

    booking = Booking.objects.get(pnr=response.data["pnr"])
    cabin = CabinConfig.objects.get(flight=booking.segments.first().flight)
    booking_class = BookingClass.objects.get(flight=cabin.flight, rbd="Y")

    assert cabin.seats_held == 1
    assert booking_class.held == 1
    assert booking_class.sold == 0
    assert booking.holds.count() == 1


def test_pnr_uses_the_unambiguous_alphabet(client, offer_id):
    pnr = create(client, offer_id).data["pnr"]
    assert set(pnr) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789")


def test_booking_emits_a_held_event_to_the_outbox(client, offer_id):
    pnr = create(client, offer_id).data["pnr"]

    event = OutboxEvent.objects.get(aggregate_id=pnr)
    assert event.event_type == "booking_held"
    assert event.processed_at is None


def test_replaying_an_idempotency_key_returns_the_first_booking(client, offer_id):
    key = str(uuid.uuid4())
    first = create(client, offer_id, key=key)
    second = create(client, offer_id, key=key)

    assert first.status_code == second.status_code == 201
    assert first.data["pnr"] == second.data["pnr"]
    assert Booking.objects.count() == 1


def test_reusing_a_key_with_a_different_body_is_rejected(client, offer_id):
    key = str(uuid.uuid4())
    create(client, offer_id, key=key)

    response = create(
        client, offer_id, key=key, passengers=[adult(first_name="Someone", last_name="Else")]
    )

    assert response.status_code == 422
    assert response.data["code"] == "idempotency_key_reuse"
    assert Booking.objects.count() == 1


def test_seats_taken_between_search_and_booking_are_a_conflict(client, offer_id):
    CabinConfig.objects.all().update(seats_sold=10)
    BookingClass.objects.all().update(sold=10)

    response = create(client, offer_id)

    assert response.status_code == 409
    assert response.data["code"] == "inventory_unavailable"
    assert not Booking.objects.exists()


def test_an_expired_offer_cannot_be_booked(client, offer_id):
    from apps.booking.models import Offer

    Offer.objects.filter(offer_id=offer_id).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    response = create(client, offer_id)

    assert response.status_code == 409
    assert response.data["code"] == "offer_expired"


def test_a_tampered_offer_cannot_be_booked(client, offer_id):
    from apps.booking.models import Offer

    offer = Offer.objects.get(offer_id=offer_id)
    offer.total_amount = 1
    offer.price_breakdown["total"] = {"amount": "1.00", "currency": "USD"}
    offer.save(update_fields=["total_amount", "price_breakdown"])

    response = create(client, offer_id)

    assert response.status_code == 409
    assert response.data["code"] == "offer_invalid"


def test_unknown_offer_is_a_conflict_not_a_crash(client, offer_id):
    response = create(client, uuid.uuid4())
    assert response.status_code == 409


def test_a_date_of_birth_must_match_the_declared_passenger_type(client, offer_id):
    toddler = adult(dob=(date.today() - timedelta(days=400)).isoformat())

    response = create(client, offer_id, passengers=[toddler])

    assert response.status_code == 422
    assert response.data["code"] == "validation_error"


def test_an_infant_needs_its_own_adult(client, offer_id):
    infant = adult(type="INF", dob=(date.today() - timedelta(days=200)).isoformat())

    response = create(client, offer_id, passengers=[adult(), infant, infant])

    assert response.status_code == 422


def test_a_booking_needs_an_adult(client, offer_id):
    child = adult(type="CHD", dob=(date.today() - timedelta(days=6 * 365)).isoformat())

    response = create(client, offer_id, passengers=[child])

    assert response.status_code == 422


def test_infants_do_not_consume_seat_inventory(client, offer_id):
    infant = adult(type="INF", dob=(date.today() - timedelta(days=200)).isoformat())

    response = create(client, offer_id, passengers=[adult(), infant])

    assert response.status_code == 201
    assert CabinConfig.objects.get().seats_held == 1


def test_creating_a_booking_requires_no_account(client, offer_id):
    assert create(client, offer_id).status_code == 201


def test_a_signed_in_traveller_owns_the_booking(client, offer_id, traveller):
    client.force_authenticate(traveller)
    pnr = create(client, offer_id).data["pnr"]

    assert Booking.objects.get(pnr=pnr).user == traveller

    response = client.get(reverse("v1:booking-detail", args=[pnr]))
    assert response.status_code == 200


def test_another_traveller_cannot_read_someone_elses_booking(client, offer_id, traveller):
    from apps.accounts.models import User

    client.force_authenticate(traveller)
    pnr = create(client, offer_id).data["pnr"]

    intruder = User.objects.create_user(email="intruder@test.local", password="test-pass-12345")
    client.force_authenticate(intruder)

    response = client.get(reverse("v1:booking-detail", args=[pnr]))
    assert response.status_code == 404


def test_a_guest_retrieves_with_pnr_and_surname(client, offer_id):
    pnr = create(client, offer_id).data["pnr"]

    ok = client.get(reverse("v1:booking-detail", args=[pnr]), {"last_name": "islam"})
    assert ok.status_code == 200
    assert ok.data["pnr"] == pnr


def test_a_wrong_surname_is_a_404_not_a_403(client, offer_id):
    """404 rather than 403: the endpoint must not confirm that a PNR exists."""
    pnr = create(client, offer_id).data["pnr"]

    response = client.get(reverse("v1:booking-detail", args=[pnr]), {"last_name": "Nobody"})
    assert response.status_code == 404


def test_expired_holds_are_released_and_the_booking_expires(client, offer_id):
    pnr = create(client, offer_id).data["pnr"]
    Booking.objects.filter(pnr=pnr).update(
        hold_expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert release_expired_holds() == 1

    booking = Booking.objects.get(pnr=pnr)
    assert booking.status == BookingStatus.EXPIRED
    assert CabinConfig.objects.get().seats_held == 0
    assert BookingClass.objects.get(rbd="Y").held == 0
    assert InventoryHold.objects.filter(booking=booking, released_at__isnull=True).count() == 0


def test_releasing_holds_twice_does_not_double_refund(client, offer_id):
    pnr = create(client, offer_id).data["pnr"]
    Booking.objects.filter(pnr=pnr).update(
        hold_expires_at=timezone.now() - timedelta(minutes=1)
    )

    release_expired_holds()
    assert release_expired_holds() == 0
    assert CabinConfig.objects.get().seats_held == 0


def test_a_live_hold_is_left_alone(client, offer_id):
    create(client, offer_id)
    assert release_expired_holds() == 0
    assert CabinConfig.objects.get().seats_held == 1
