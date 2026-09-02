"""The oversell and double-charge invariants, proven through the API rather than under it.

`inventory/tests/test_availability.py` races `availability.hold()` directly. These race the
endpoint a customer actually calls, so offer re-validation, multi-leg holds, PNR minting and the
idempotency layer are all inside the contended window (SPEC.md §14.1, §14.2, §14.4, §14.8).

Every case is `transaction=True`: the default test transaction hides row-lock behaviour, so a
test without it proves nothing about locking.
"""

import json
import threading
import uuid

import pytest
from django.core.cache import cache
from django.db import connections
from django.urls import reverse
from rest_framework.test import APIClient

from apps.booking.models import Booking
from apps.inventory.models import BookingClass, CabinConfig
from apps.payments.models import Payment, ProviderWebhookEvent
from apps.payments.providers import get_provider

THREADS = 8

PASSENGER = {
    "type": "ADT",
    "first_name": "Nazmul",
    "last_name": "Islam",
    "dob": "1990-05-14",
}


def search_offer(client: APIClient, origin: str, destination: str, day) -> str:
    response = client.post(
        reverse("v1:search-flights"),
        {
            "trip_type": "ONE_WAY",
            "slices": [
                {"origin": origin, "destination": destination, "date": day.isoformat()}
            ],
            "passengers": {"adults": 1, "children": 0, "infants": 0},
            "cabin": "ECONOMY",
            "currency": "USD",
            "max_stops": 0,
        },
        format="json",
    )
    return response.data["slices"][0]["offers"][0]["offer_id"]


def post_booking(client: APIClient, body: dict, key: str):
    return client.post(
        reverse("v1:booking-create"), body, format="json", HTTP_IDEMPOTENCY_KEY=key
    )


def one_way_body(offer_id: str) -> dict:
    return {
        "offer_id": str(offer_id),
        "passengers": [PASSENGER],
        "contact": {"email": "traveller@example.com"},
    }


def race(work, threads: int = THREADS) -> list:
    """Run ``work`` on N threads that start together, and collect what each returned.

    The barrier is what makes this a race rather than N sequential calls, and closing the
    connection in `finally` stops a thread leaving one checked out of the pool.
    """
    outcomes: list = []
    guard = threading.Lock()
    barrier = threading.Barrier(threads)

    def attempt(index: int) -> None:
        barrier.wait()
        try:
            result = work(index)
        except Exception as exc:
            result = f"error:{exc!r}"
        finally:
            connections.close_all()
        with guard:
            outcomes.append(result)

    workers = [threading.Thread(target=attempt, args=(index,)) for index in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)

    return outcomes


# --- §14.1 no oversell, through the front door -------------------------------


@pytest.mark.django_db(transaction=True)
def test_the_last_seat_is_sold_once_through_the_api(make_flight, make_fare):
    """SPEC.md §14.1 and M3's acceptance: exactly one booking, everyone else gets 409."""
    flight = make_flight(days_ahead=20, capacity=1, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client = APIClient()
    offer_id = search_offer(client, "DAC", "DXB", flight.departure_local.date())

    def book(_index: int) -> int:
        # A client per thread: APIClient is not built to be shared across them.
        return post_booking(
            APIClient(), one_way_body(offer_id), str(uuid.uuid4())
        ).status_code

    outcomes = race(book)

    assert outcomes.count(201) == 1, outcomes
    assert outcomes.count(409) == THREADS - 1, outcomes

    assert Booking.objects.count() == 1
    assert CabinConfig.objects.get(flight=flight).seats_held == 1
    assert BookingClass.objects.get(flight=flight, rbd="Y").held == 1


@pytest.mark.django_db(transaction=True)
def test_losing_the_return_leg_leaves_no_outbound_seat_held(make_flight, make_fare):
    """The multi-leg form of the same invariant, under contention.

    The outbound has room for everyone and the return has one seat, so every thread can take an
    outbound seat and only one can complete. A loser holding an outbound seat would be inventory
    nobody can sell and a journey nobody can fly.
    """
    outbound = make_flight(days_ahead=20, capacity=THREADS, rbd="Y", flight_number="101")
    inbound = make_flight(
        origin="DXB", destination="DAC", days_ahead=27, capacity=1, rbd="Y",
        flight_number="102",
    )
    make_fare(rbd="Y", amount="200.00")
    make_fare(origin="DXB", destination="DAC", rbd="Y", amount="180.00")

    client = APIClient()
    slices = client.post(
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
    ).data["slices"]

    body = {
        "offer_ids": [
            slices[0]["offers"][0]["offer_id"],
            slices[1]["offers"][0]["offer_id"],
        ],
        "passengers": [PASSENGER],
        "contact": {"email": "traveller@example.com"},
    }

    def book(_index: int) -> int:
        return post_booking(APIClient(), body, str(uuid.uuid4())).status_code

    outcomes = race(book)

    assert outcomes.count(201) == 1, outcomes
    assert Booking.objects.count() == 1

    # The winner holds one seat on each leg; every loser holds nothing on either.
    assert CabinConfig.objects.get(flight=outbound).seats_held == 1
    assert CabinConfig.objects.get(flight=inbound).seats_held == 1


# --- §14.4 idempotency under a real race -------------------------------------


@pytest.mark.django_db(transaction=True)
def test_one_key_sent_twice_at_once_books_once(make_flight, make_fare):
    """The key is claimed before the work, so a concurrent duplicate cannot book a second time.

    Writing the key *after* the view instead let both callers run it: one PNR was returned and a
    second, invisible booking sat holding a seat until its hold expired.
    """
    flight = make_flight(days_ahead=20, capacity=5, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client = APIClient()
    offer_id = search_offer(client, "DAC", "DXB", flight.departure_local.date())

    key = str(uuid.uuid4())
    body = one_way_body(offer_id)

    def book(_index: int):
        response = post_booking(APIClient(), body, key)
        payload = response.data or {}
        return (response.status_code, payload.get("pnr") or payload.get("code"))

    outcomes = race(book, threads=2)

    created = [entry for entry in outcomes if entry[0] == 201]
    assert len(created) == 1, outcomes

    # The loser is told to retry rather than being handed a second booking. If the winner had
    # already finished, a replay of its 201 is equally correct.
    for status, detail in outcomes:
        assert status in (201, 409), outcomes
        if status == 409:
            assert detail == "idempotency_in_progress", outcomes

    assert Booking.objects.count() == 1
    assert CabinConfig.objects.get(flight=flight).seats_held == 1


@pytest.mark.django_db(transaction=True)
def test_a_failed_request_frees_its_key_for_a_retry(make_flight, make_fare):
    """Claiming up front must not strand the key when the work itself fails."""
    flight = make_flight(days_ahead=20, capacity=1, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client = APIClient()
    offer_id = search_offer(client, "DAC", "DXB", flight.departure_local.date())

    CabinConfig.objects.filter(flight=flight).update(seats_sold=1)
    BookingClass.objects.filter(flight=flight).update(sold=1)

    key = str(uuid.uuid4())
    body = one_way_body(offer_id)

    assert post_booking(client, body, key).status_code == 409

    # Seats come back, and the same key works — the failed attempt left nothing claimed.
    CabinConfig.objects.filter(flight=flight).update(seats_sold=0)
    BookingClass.objects.filter(flight=flight).update(sold=0)

    assert post_booking(client, body, key).status_code == 201


# --- §14.2 duplicate webhook delivery ----------------------------------------


@pytest.mark.django_db(transaction=True)
def test_a_webhook_delivered_twice_at_once_charges_once(
    make_flight, make_fare, celery_eager
):
    """Providers redeliver, sometimes concurrently. The unique index is what decides."""
    flight = make_flight(days_ahead=20, capacity=5, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client = APIClient()
    offer_id = search_offer(client, "DAC", "DXB", flight.departure_local.date())
    pnr = post_booking(client, one_way_body(offer_id), str(uuid.uuid4())).data["pnr"]

    intent = client.post(
        reverse("v1:payment-intent-create", args=[pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data

    provider = get_provider("sandbox")
    body = json.dumps(
        {
            "id": "sbx_evt_race",
            "type": "payment_intent.succeeded",
            "data": {
                "intent_id": intent["provider_intent_id"],
                "charge_id": "sbx_ch_race",
                "amount": intent["amount"]["amount"],
                "currency": "USD",
                "card_brand": "VISA",
                "card_last4": "4242",
            },
        },
        sort_keys=True,
    ).encode()
    signature = provider.sign(body)

    def deliver(_index: int) -> int:
        return APIClient().post(
            reverse("v1:payment-webhook", args=["sandbox"]),
            data=body,
            content_type="application/json",
            HTTP_X_WAYFARE_SIGNATURE=signature,
        ).status_code

    outcomes = race(deliver, threads=2)

    assert set(outcomes) == {202}, outcomes
    assert ProviderWebhookEvent.objects.filter(provider_event_id="sbx_evt_race").count() == 1
    assert Payment.objects.filter(provider_charge_id="sbx_ch_race").count() == 1

    booking = Booking.objects.get(pnr=pnr)
    assert booking.paid_amount == booking.total_amount


# --- §14.8 guest retrieval is rate limited -----------------------------------


@pytest.mark.django_db(transaction=True)
def test_guest_retrieval_is_rate_limited(make_flight, make_fare):
    """A PNR is six characters — without a limit, the surname check is brute-forceable."""
    flight = make_flight(days_ahead=20, capacity=5, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client = APIClient()
    offer_id = search_offer(client, "DAC", "DXB", flight.departure_local.date())
    pnr = post_booking(client, one_way_body(offer_id), str(uuid.uuid4())).data["pnr"]

    # The throttle counts in the same cache the autouse fixture resets, so start from zero.
    cache.clear()

    url = reverse("v1:booking-detail", args=[pnr])
    statuses = [
        APIClient().get(url, {"last_name": "Wrong"}).status_code for _ in range(7)
    ]

    assert 429 in statuses, statuses
    # The configured bucket is 5 per 15 minutes, so the sixth attempt is the first refusal.
    assert statuses.index(429) == 5, statuses

    cache.clear()
