"""Cancel, refund, void and exchange — SPEC.md §6.4."""

import uuid
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.constants import RoleCode
from apps.accounts.models import User, UserRole
from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.inventory.models import BookingClass, CabinConfig
from apps.ops.models import OutboxEvent
from apps.payments.constants import LedgerEntryType, RefundStatus
from apps.payments.models import LedgerEntry, Refund
from apps.ticketing.constants import CouponStatus, TicketStatus
from apps.ticketing.models import Ticket

pytestmark = pytest.mark.django_db

GOOD_CARD = "4242424242424242"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def finance(db):
    user = User.objects.create_user(email="finance@test.local", password="test-pass-12345")
    UserRole.objects.create(user=user, role=RoleCode.FINANCE)
    return user


def _search(client, flight, days_ahead=None):
    return client.post(
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


@pytest.fixture
def paid_booking(client, make_flight, make_fare, fare_family, celery_eager):
    """A TICKETED booking with money taken and seats sold."""
    fare_family.refundable = True
    fare_family.refund_fee = Decimal("40.00")
    fare_family.changeable = True
    fare_family.change_fee = Decimal("60.00")
    fare_family.save()

    flight = make_flight(days_ahead=30, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")
    offer_id = _search(client, flight)

    pnr = client.post(
        reverse("v1:booking-create"),
        {
            "offer_id": offer_id,
            "passengers": [
                {"type": "ADT", "first_name": "Nazmul", "last_name": "Islam",
                 "dob": "1990-05-14"}
            ],
            "contact": {"email": "traveller@example.com"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data["pnr"]

    intent = client.post(
        reverse("v1:payment-intent-create", args=[pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data
    client.post(
        reverse("v1:payment-intent-confirm", args=[pnr, intent["intent_id"]]),
        {"card_number": GOOD_CARD, "last_name": "Islam"},
        format="json",
    )
    return Booking.objects.get(pnr=pnr)


def age_ticket(days: int = 1) -> None:
    """Push the ticket out of the void window so the penalty ladder applies."""
    Ticket.objects.update(issued_at=timezone.now() - timezone.timedelta(days=days))


def cancel(client, booking, **body):
    payload = {"last_name": "Islam"}
    payload.update(body)
    return client.post(
        reverse("v1:booking-cancel", args=[booking.pnr]),
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


# --- cancel + refund ---------------------------------------------------------


def test_quote_only_shows_the_penalty_without_cancelling(client, paid_booking):
    response = cancel(client, paid_booking, quote_only=True)

    assert response.status_code == 200
    assert response.data["quote"]["penalty"]["amount"] == "40.00"
    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.TICKETED
    assert not Refund.objects.exists()


def test_cancelling_releases_the_seats_and_opens_a_refund(client, paid_booking, celery_eager):
    age_ticket()
    response = cancel(client, paid_booking)

    assert response.status_code == 200

    cabin = CabinConfig.objects.get()
    booking_class = BookingClass.objects.get(rbd="Y")
    assert (cabin.seats_sold, cabin.seats_held) == (0, 0)
    assert (booking_class.sold, booking_class.held) == (0, 0)

    refund = Refund.objects.get()
    assert refund.penalty_amount == Decimal("40.00")


def test_a_small_refund_is_auto_approved_and_processed(client, paid_booking, celery_eager):
    """Under REFUND_AUTO_APPROVE_LIMIT it goes straight through, no ops decision."""
    cancel(client, paid_booking)

    refund = Refund.objects.get()
    assert refund.status == RefundStatus.PROCESSED
    assert refund.provider_refund_id

    booking = Booking.objects.get(pk=paid_booking.pk)
    assert booking.status == BookingStatus.REFUNDED


def test_a_large_refund_waits_for_finance(
    client, paid_booking, celery_eager, settings
):
    settings.REFUND_AUTO_APPROVE_LIMIT = 1

    cancel(client, paid_booking)

    refund = Refund.objects.get()
    assert refund.status == RefundStatus.REQUESTED
    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.REFUND_PENDING
    assert OutboxEvent.objects.filter(event_type="refund_requested").exists()


def test_refunding_closes_the_coupons(client, paid_booking, celery_eager):
    cancel(client, paid_booking)

    ticket = Ticket.objects.get()
    assert ticket.status == TicketStatus.REFUNDED
    assert list(ticket.coupons.values_list("status", flat=True)) == [CouponStatus.REFUNDED]


def test_the_ledger_records_the_refund_and_penalty(client, paid_booking, celery_eager):
    age_ticket()
    cancel(client, paid_booking)

    types = list(LedgerEntry.objects.order_by("created_at").values_list("entry_type", flat=True))
    assert types == [
        LedgerEntryType.SALE,
        LedgerEntryType.PAYMENT,
        LedgerEntryType.REFUND,
        LedgerEntryType.PENALTY,
    ]


def test_cancelling_twice_does_not_open_a_second_refund(client, paid_booking, celery_eager):
    cancel(client, paid_booking)
    second = cancel(client, paid_booking)

    assert second.status_code == 409
    assert Refund.objects.count() == 1


def test_a_stranger_cannot_cancel_a_booking(client, paid_booking, traveller):
    client.force_authenticate(traveller)
    response = client.post(
        reverse("v1:booking-cancel", args=[paid_booking.pnr]),
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.TICKETED


# --- void --------------------------------------------------------------------


def test_a_same_day_cancellation_is_a_void_with_no_penalty(
    client, paid_booking, celery_eager
):
    """Issued today with every coupon open: the money comes back in full."""
    response = cancel(client, paid_booking)

    assert response.data["voided"] is True
    assert response.data["quote"]["penalty"]["amount"] == "0.00"
    assert response.data["quote"]["refundable"]["amount"] == "200.00"


def test_a_ticket_issued_yesterday_is_not_voidable(client, paid_booking, celery_eager):
    age_ticket()

    response = cancel(client, paid_booking)

    assert response.data["voided"] is False
    assert response.data["quote"]["penalty"]["amount"] == "40.00"


# --- ops refund queue --------------------------------------------------------


def test_finance_sees_and_approves_the_queue(
    client, paid_booking, celery_eager, finance, settings
):
    settings.REFUND_AUTO_APPROVE_LIMIT = 1
    cancel(client, paid_booking)
    refund = Refund.objects.get()

    client.force_authenticate(finance)
    queue = client.get(reverse("v1:ops-refund-queue"))
    assert queue.status_code == 200
    assert queue.data[0]["pnr"] == paid_booking.pnr

    approved = client.post(
        reverse("v1:ops-refund-approve", args=[refund.public_id]), {}, format="json"
    )
    assert approved.status_code == 200

    refund.refresh_from_db()
    assert refund.status == RefundStatus.PROCESSED
    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.REFUNDED


def test_finance_can_reject_a_refund(client, paid_booking, celery_eager, finance, settings):
    settings.REFUND_AUTO_APPROVE_LIMIT = 1
    cancel(client, paid_booking)
    refund = Refund.objects.get()

    client.force_authenticate(finance)
    response = client.post(
        reverse("v1:ops-refund-reject", args=[refund.public_id]),
        {"reason": "outside the fare rule"},
        format="json",
    )

    assert response.status_code == 200
    refund.refresh_from_db()
    assert refund.status == RefundStatus.REJECTED
    # The booking stays cancelled; the money simply is not returned.
    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.REFUND_PENDING


def test_the_refund_queue_is_closed_to_travellers(client, paid_booking, traveller):
    client.force_authenticate(traveller)
    assert client.get(reverse("v1:ops-refund-queue")).status_code == 403


def test_the_refund_queue_is_closed_to_anonymous_callers(client):
    assert client.get(reverse("v1:ops-refund-queue")).status_code in (401, 403)


def test_approving_twice_is_refused(client, paid_booking, celery_eager, finance, settings):
    settings.REFUND_AUTO_APPROVE_LIMIT = 1
    cancel(client, paid_booking)
    refund = Refund.objects.get()

    client.force_authenticate(finance)
    client.post(reverse("v1:ops-refund-approve", args=[refund.public_id]), {}, format="json")
    again = client.post(
        reverse("v1:ops-refund-approve", args=[refund.public_id]), {}, format="json"
    )

    assert again.status_code == 409
    assert Refund.objects.count() == 1


# --- change / exchange -------------------------------------------------------


@pytest.fixture
def new_offer(client, make_flight, make_fare):
    """A second, dearer flight to exchange onto."""
    flight = make_flight(days_ahead=45, capacity=10, rbd="B", flight_number="102")
    make_fare(rbd="B", amount="260.00")
    return _search(client, flight), flight


def change_quote(client, booking, offer_id):
    return client.post(
        reverse("v1:booking-change-quote", args=[booking.pnr]),
        {"offer_id": offer_id, "last_name": "Islam"},
        format="json",
    )


def change_confirm(client, booking, offer_id):
    return client.post(
        reverse("v1:booking-change-confirm", args=[booking.pnr]),
        {"offer_id": offer_id, "last_name": "Islam"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


def test_a_change_quote_prices_the_difference_plus_the_fee(
    client, paid_booking, new_offer, celery_eager
):
    offer_id, _ = new_offer

    response = change_quote(client, paid_booking, offer_id)

    assert response.status_code == 200
    assert response.data["changeable"] is True
    assert response.data["fare_difference"]["amount"] == "60.00"
    assert response.data["change_fee"]["amount"] == "60.00"
    assert response.data["amount_due"]["amount"] == "120.00"


def test_a_change_quote_changes_nothing(client, paid_booking, new_offer, celery_eager):
    offer_id, _ = new_offer
    change_quote(client, paid_booking, offer_id)

    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.TICKETED
    assert Ticket.objects.count() == 1


def test_a_non_changeable_fare_is_refused(
    client, paid_booking, new_offer, fare_family, celery_eager
):
    fare_family.changeable = False
    fare_family.save()
    offer_id, _ = new_offer

    response = change_confirm(client, paid_booking, offer_id)

    assert response.status_code == 422
    assert response.data["code"] == "fare_rule_violation"
    assert Booking.objects.get(pk=paid_booking.pk).status == BookingStatus.TICKETED


def test_confirming_a_change_moves_the_seats_and_awaits_the_delta(
    client, paid_booking, new_offer, celery_eager
):
    offer_id, new_flight = new_offer
    old_flight_id = paid_booking.segments.first().flight_id

    response = change_confirm(client, paid_booking, offer_id)

    assert response.status_code == 200
    booking = Booking.objects.get(pk=paid_booking.pk)
    assert booking.status == BookingStatus.CHANGE_PENDING

    # The new seat is held, and the old one stays sold: an exchange nobody pays for must
    # leave the passenger on the flight they already hold a ticket for.
    old_cabin = CabinConfig.objects.get(flight_id=old_flight_id)
    new_class = BookingClass.objects.get(flight=new_flight, rbd="B")
    assert old_cabin.seats_sold == 1
    assert new_class.held == 1

    # Balance owing is the delta, collected through the ordinary payment flow.
    assert booking.total_amount - booking.paid_amount == Decimal("120.00")


def test_paying_the_delta_reissues_with_conjunction_linkage(
    client, paid_booking, new_offer, celery_eager
):
    offer_id, new_flight = new_offer
    original = Ticket.objects.get()

    change_confirm(client, paid_booking, offer_id)

    intent = client.post(
        reverse("v1:payment-intent-create", args=[paid_booking.pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data
    assert intent["amount"]["amount"] == "120.00"

    client.post(
        reverse("v1:payment-intent-confirm", args=[paid_booking.pnr, intent["intent_id"]]),
        {"card_number": GOOD_CARD, "last_name": "Islam"},
        format="json",
    )

    booking = Booking.objects.get(pk=paid_booking.pk)
    assert booking.status == BookingStatus.TICKETED

    original.refresh_from_db()
    assert original.status == TicketStatus.EXCHANGED
    assert list(original.coupons.values_list("status", flat=True)) == [CouponStatus.EXCHANGED]

    reissued = Ticket.objects.exclude(pk=original.pk).get()
    assert reissued.conjunction_of_id == original.pk
    assert reissued.status == TicketStatus.ISSUED
    assert reissued.coupons.first().segment.flight_id == new_flight.id

    # The new seat is sold, not merely held.
    assert BookingClass.objects.get(flight=new_flight, rbd="B").sold == 1


def test_a_cheaper_change_completes_without_payment(
    client, paid_booking, make_flight, make_fare, fare_family, celery_eager
):
    """No money owed, so the reissue happens immediately rather than waiting on a payment."""
    fare_family.change_fee = Decimal("0.00")
    fare_family.save()

    cheaper = make_flight(days_ahead=50, capacity=10, rbd="L", flight_number="103")
    make_fare(rbd="L", amount="120.00")
    offer_id = _search(client, cheaper)

    response = change_confirm(client, paid_booking, offer_id)

    assert response.status_code == 200
    assert response.data["quote"]["amount_due"]["amount"] == "0.00"

    booking = Booking.objects.get(pk=paid_booking.pk)
    assert booking.status == BookingStatus.TICKETED
    assert Ticket.objects.filter(status=TicketStatus.ISSUED).count() == 1
    assert Ticket.objects.filter(status=TicketStatus.EXCHANGED).count() == 1


def test_residual_value_is_reported_when_the_family_allows_it(
    client, paid_booking, make_flight, make_fare, fare_family, celery_eager
):
    fare_family.change_fee = Decimal("0.00")
    fare_family.allows_residual_value = True
    fare_family.save()

    cheaper = make_flight(days_ahead=50, capacity=10, rbd="L", flight_number="104")
    make_fare(rbd="L", amount="120.00")
    offer_id = _search(client, cheaper)

    response = change_quote(client, paid_booking, offer_id)

    assert response.data["amount_due"]["amount"] == "0.00"
    assert response.data["residual"]["amount"] == "80.00"


def test_an_unticketed_booking_cannot_be_exchanged(
    client, make_flight, make_fare, new_offer, celery_eager
):
    """Before ticketing it is cheaper to cancel and rebook, so the exchange path refuses."""
    flight = make_flight(days_ahead=30, capacity=10, rbd="Q", flight_number="105")
    make_fare(rbd="Q", amount="150.00")
    offer_id = _search(client, flight)

    pnr = client.post(
        reverse("v1:booking-create"),
        {
            "offer_id": offer_id,
            "passengers": [
                {"type": "ADT", "first_name": "Held", "last_name": "Islam",
                 "dob": "1990-05-14"}
            ],
            "contact": {"email": "held@example.com"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data["pnr"]

    response = client.post(
        reverse("v1:booking-change-confirm", args=[pnr]),
        {"offer_id": new_offer[0], "last_name": "Islam"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 409
    assert response.data["code"] == "invalid_transition"


def test_an_abandoned_change_leaves_the_original_journey_intact(
    client, paid_booking, new_offer, celery_eager
):
    """Nobody paid the delta: the proposed seats go back and the old ticket still stands."""
    from apps.booking.tasks import release_expired_holds

    offer_id, new_flight = new_offer
    old_flight_id = paid_booking.segments.first().flight_id

    change_confirm(client, paid_booking, offer_id)
    Booking.objects.filter(pk=paid_booking.pk).update(
        hold_expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )

    assert release_expired_holds() == 1

    booking = Booking.objects.get(pk=paid_booking.pk)
    assert booking.status == BookingStatus.TICKETED
    assert CabinConfig.objects.get(flight_id=old_flight_id).seats_sold == 1
    assert BookingClass.objects.get(flight=new_flight, rbd="B").held == 0
    assert booking.segments.count() == 1
    assert Ticket.objects.get().status == TicketStatus.ISSUED


def test_the_ledger_reconciles_after_an_exchange(
    client, paid_booking, new_offer, celery_eager
):
    """M5 acceptance: the running balance nets to zero once the delta is paid."""
    offer_id, _ = new_offer
    change_confirm(client, paid_booking, offer_id)

    intent = client.post(
        reverse("v1:payment-intent-create", args=[paid_booking.pnr]),
        {},
        format="json",
        QUERY_STRING="last_name=Islam",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).data
    client.post(
        reverse("v1:payment-intent-confirm", args=[paid_booking.pnr, intent["intent_id"]]),
        {"card_number": GOOD_CARD, "last_name": "Islam"},
        format="json",
    )

    entries = list(LedgerEntry.objects.order_by("created_at"))
    assert [entry.entry_type for entry in entries] == [
        LedgerEntryType.SALE,
        LedgerEntryType.PAYMENT,
        LedgerEntryType.ADJUSTMENT,
        LedgerEntryType.PAYMENT,
    ]
    assert entries[-1].balance_after == Decimal("0.00")

    # The ledger is re-derivable by replaying it, which is the point of append-only.
    replayed = sum(entry.debit - entry.credit for entry in entries)
    assert replayed == Decimal("0.00")

    booking = Booking.objects.get(pk=paid_booking.pk)
    assert booking.paid_amount == booking.total_amount
