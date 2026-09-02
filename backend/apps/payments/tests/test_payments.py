import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.booking.constants import BookingStatus, SegmentStatus
from apps.booking.models import Booking
from apps.inventory.models import BookingClass, CabinConfig
from apps.ops.models import OutboxEvent
from apps.payments.constants import IntentStatus, LedgerEntryType, PaymentStatus
from apps.payments.models import LedgerEntry, Payment, PaymentIntent, ProviderWebhookEvent
from apps.payments.providers import get_provider
from apps.ticketing.models import Ticket

pytestmark = pytest.mark.django_db

GOOD_CARD = "4242424242424242"
DECLINED_CARD = "4000000000000002"
THREE_DS_CARD = "4000000000003220"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def held_booking(client, make_flight, make_fare):
    """A real HELD booking with real inventory behind it."""
    flight = make_flight(days_ahead=30, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    search = client.post(
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
    offer_id = search.data["slices"][0]["offers"][0]["offer_id"]

    created = client.post(
        reverse("v1:booking-create"),
        {
            "offer_id": offer_id,
            "passengers": [
                {
                    "type": "ADT",
                    "first_name": "Nazmul",
                    "last_name": "Islam",
                    "dob": "1990-05-14",
                }
            ],
            "contact": {"email": "traveller@example.com"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    return Booking.objects.get(pnr=created.data["pnr"])


def open_intent(client, booking) -> dict:
    response = client.post(
        reverse("v1:payment-intent-create", args=[booking.pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code == 201, response.data
    return response.data


def confirm(client, booking, intent, card=GOOD_CARD):
    return client.post(
        reverse("v1:payment-intent-confirm", args=[booking.pnr, intent["intent_id"]]),
        {"card_number": card, "last_name": "Islam"},
        format="json",
    )


def test_an_intent_is_opened_for_the_outstanding_balance(client, held_booking):
    intent = open_intent(client, held_booking)

    assert intent["amount"] == {"amount": "200.00", "currency": "USD"}
    assert intent["status"] == IntentStatus.REQUIRES_PAYMENT
    assert intent["client_secret"]


def test_a_second_intent_reuses_the_live_one(client, held_booking):
    """Two tabs on the card form must not become two charges."""
    first = open_intent(client, held_booking)
    second = open_intent(client, held_booking)

    assert first["provider_intent_id"] == second["provider_intent_id"]
    assert PaymentIntent.objects.count() == 1


def test_an_expired_hold_cannot_be_paid_for(client, held_booking):
    Booking.objects.filter(pk=held_booking.pk).update(
        hold_expires_at=timezone.now() - timedelta(minutes=1)
    )
    response = client.post(
        reverse("v1:payment-intent-create", args=[held_booking.pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code == 409


def test_paying_sells_the_seats_and_issues_tickets(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    response = confirm(client, held_booking, intent)

    assert response.status_code == 202

    booking = Booking.objects.get(pk=held_booking.pk)
    assert booking.status == BookingStatus.TICKETED
    assert booking.paid_amount == Decimal("200.00")
    assert booking.hold_expires_at is None

    cabin = CabinConfig.objects.get()
    booking_class = BookingClass.objects.get(rbd="Y")
    assert (cabin.seats_held, cabin.seats_sold) == (0, 1)
    assert (booking_class.held, booking_class.sold) == (0, 1)

    assert booking.segments.first().status == SegmentStatus.CONFIRMED
    assert not booking.holds.filter(released_at__isnull=True).exists()


def test_payment_records_the_card_fingerprint_but_never_the_number(
    client, held_booking, celery_eager
):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent)

    payment = Payment.objects.get()
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.card_brand == "VISA"
    assert payment.card_last4 == "4242"

    stored = json.dumps(
        [payment.provider_charge_id, payment.card_last4, payment.card_brand]
        + [event.payload for event in ProviderWebhookEvent.objects.all()]
    )
    assert GOOD_CARD not in stored


def test_the_ledger_balances_to_zero(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent)

    entries = list(LedgerEntry.objects.order_by("created_at"))
    assert [entry.entry_type for entry in entries] == [
        LedgerEntryType.SALE,
        LedgerEntryType.PAYMENT,
    ]
    assert entries[-1].balance_after == Decimal("0.00")


def test_tickets_are_issued_with_a_coupon_per_segment(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent)

    ticket = Ticket.objects.get()
    assert len(ticket.ticket_number) == 13
    assert ticket.coupons.count() == held_booking.segments.count()
    assert ticket.total_amount == Decimal("200.00")


def test_a_declined_card_leaves_the_hold_intact(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent, card=DECLINED_CARD)

    booking = Booking.objects.get(pk=held_booking.pk)
    assert booking.status == BookingStatus.HELD
    assert booking.paid_amount == Decimal("0.00")
    assert Payment.objects.get().status == PaymentStatus.FAILED
    assert CabinConfig.objects.get().seats_held == 1
    assert not Ticket.objects.exists()


def test_a_card_needing_3ds_stops_at_requires_action(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    response = confirm(client, held_booking, intent, card=THREE_DS_CARD)

    assert response.data["status"] == IntentStatus.REQUIRES_ACTION
    assert response.data["three_ds_status"] == "REQUIRED"
    assert not Payment.objects.exists()
    assert Booking.objects.get(pk=held_booking.pk).status == BookingStatus.HELD


def test_a_replayed_webhook_does_not_pay_twice(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent)

    event = ProviderWebhookEvent.objects.get()
    body = json.dumps(
        {"id": event.provider_event_id, "type": event.event_type, "data": event.payload},
        sort_keys=True,
    ).encode()
    provider = get_provider("sandbox")

    replay = client.post(
        reverse("v1:payment-webhook", args=["sandbox"]),
        data=body,
        content_type="application/json",
        HTTP_X_WAYFARE_SIGNATURE=provider.sign(body),
    )

    assert replay.status_code == 202
    assert ProviderWebhookEvent.objects.count() == 1
    assert Payment.objects.count() == 1
    assert Booking.objects.get(pk=held_booking.pk).paid_amount == Decimal("200.00")


def test_an_unsigned_webhook_is_rejected(client):
    response = client.post(
        reverse("v1:payment-webhook", args=["sandbox"]),
        data=b'{"id": "evt_forged", "type": "payment_intent.succeeded", "data": {}}',
        content_type="application/json",
        HTTP_X_WAYFARE_SIGNATURE="not-the-signature",
    )

    assert response.status_code == 400
    assert not ProviderWebhookEvent.objects.exists()


def test_payments_are_listed_for_the_booking(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent)

    response = client.get(
        reverse("v1:payment-list", args=[held_booking.pnr]), {"last_name": "Islam"}
    )

    assert response.status_code == 200
    assert response.data[0]["status"] == PaymentStatus.CAPTURED
    assert response.data[0]["card_last4"] == "4242"


def test_another_traveller_cannot_open_an_intent(client, held_booking, traveller):
    client.force_authenticate(traveller)
    response = client.post(
        reverse("v1:payment-intent-create", args=[held_booking.pnr]),
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code == 404


def test_confirmation_emits_the_booking_events(client, held_booking, celery_eager):
    intent = open_intent(client, held_booking)
    confirm(client, held_booking, intent)

    types = set(
        OutboxEvent.objects.filter(aggregate_id=held_booking.pnr).values_list(
            "event_type", flat=True
        )
    )
    assert {"booking_held", "booking_confirmed", "ticket_issued"} <= types


def test_paying_after_the_hold_expired_queues_a_refund(client, held_booking, celery_eager):
    """The seats are gone; keeping the money silently would be the worst possible outcome."""
    from apps.booking.tasks import release_expired_holds
    from apps.payments.models import Refund

    intent = open_intent(client, held_booking)
    Booking.objects.filter(pk=held_booking.pk).update(
        hold_expires_at=timezone.now() - timedelta(minutes=1)
    )
    release_expired_holds()

    confirm(client, held_booking, intent)

    booking = Booking.objects.get(pk=held_booking.pk)
    assert booking.status == BookingStatus.EXPIRED
    assert not Ticket.objects.exists()

    # Seats stayed released rather than being quietly re-taken.
    cabin = CabinConfig.objects.get()
    assert (cabin.seats_held, cabin.seats_sold) == (0, 0)

    refund = Refund.objects.get()
    assert refund.status == "REQUESTED"
    assert refund.amount == Decimal("200.00")
    assert OutboxEvent.objects.filter(event_type="payment_requires_refund").exists()
