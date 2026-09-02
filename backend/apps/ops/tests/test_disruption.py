"""Detection, rebooking options and acceptance — SPEC.md §6.5."""

import uuid

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.constants import RoleCode
from apps.accounts.models import User, UserRole
from apps.booking.constants import BookingStatus, SegmentStatus
from apps.booking.models import Booking
from apps.inventory.constants import FlightStatus
from apps.inventory.models import BookingClass, CabinConfig
from apps.ops.constants import DisruptionType, RebookOptionStatus
from apps.ops.models import Disruption, OutboxEvent, RebookOption
from apps.ops.services.disruption import classify, detect, sweep
from apps.ops.tasks import detect_disruptions
from apps.ticketing.constants import CouponStatus, TicketStatus
from apps.ticketing.models import Ticket

pytestmark = pytest.mark.django_db

GOOD_CARD = "4242424242424242"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def ops_agent(db):
    user = User.objects.create_user(email="ops@test.local", password="test-pass-12345")
    UserRole.objects.create(user=user, role=RoleCode.OPS_AGENT)
    return user


def _book_and_pay(client, flight) -> Booking:
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


@pytest.fixture
def disrupted(client, make_flight, make_fare, celery_eager):
    """A ticketed booking whose flight is then cancelled, with alternatives available."""
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y", depart_hour=8)
    make_fare(rbd="Y", amount="200.00")
    booking = _book_and_pay(client, flight)

    # Alternatives on the same day and the day after.
    make_flight(days_ahead=20, capacity=10, rbd="Y", depart_hour=14, flight_number="201")
    make_flight(days_ahead=21, capacity=10, rbd="Y", depart_hour=8, flight_number="202")

    flight.status = FlightStatus.CANCELLED
    flight.save(update_fields=["status"])
    return booking, flight


# --- detection ---------------------------------------------------------------


def test_a_short_delay_is_not_a_disruption(make_flight):
    flight = make_flight(days_ahead=10, capacity=5, rbd="Y")
    flight.delay_minutes = 45
    flight.save(update_fields=["delay_minutes"])

    assert classify(flight) is None
    assert detect(flight) is None


def test_a_long_delay_is_a_disruption(make_flight):
    flight = make_flight(days_ahead=10, capacity=5, rbd="Y")
    flight.delay_minutes = 121
    flight.save(update_fields=["delay_minutes"])

    disruption = detect(flight)

    assert disruption is not None
    assert disruption.type == DisruptionType.DELAY
    assert disruption.delay_minutes == 121


def test_a_cancellation_is_a_disruption(make_flight):
    flight = make_flight(days_ahead=10, capacity=5, rbd="Y")
    flight.status = FlightStatus.CANCELLED
    flight.save(update_fields=["status"])

    assert detect(flight).type == DisruptionType.CANCELLATION


def test_the_same_flight_is_not_flagged_twice(make_flight):
    """The detector runs every five minutes; a passenger gets one notice, not twelve an hour."""
    flight = make_flight(days_ahead=10, capacity=5, rbd="Y")
    flight.status = FlightStatus.CANCELLED
    flight.save(update_fields=["status"])

    assert detect(flight) is not None
    assert detect(flight) is None
    assert Disruption.objects.count() == 1


def test_the_sweep_is_idempotent(disrupted, celery_eager):
    first = detect_disruptions()
    second = detect_disruptions()

    assert first["disruptions"] == 1
    assert second["disruptions"] == 0
    assert Disruption.objects.count() == 1


# --- options -----------------------------------------------------------------


def test_a_disrupted_booking_is_offered_alternatives(disrupted, celery_eager):
    booking, flight = disrupted

    totals = sweep()

    assert totals["bookings_notified"] == 1
    options = RebookOption.objects.filter(booking=booking)
    assert 1 <= options.count() <= 3
    assert all(option.fare_delta == 0 for option in options)
    assert flight.id not in {option.proposed_flight_id for option in options}


def test_at_most_three_options_are_offered(client, make_flight, make_fare, celery_eager):
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y", depart_hour=6)
    make_fare(rbd="Y", amount="200.00")
    _book_and_pay(client, flight)

    for hour in (8, 10, 12, 14, 16):
        make_flight(
            days_ahead=20, capacity=10, rbd="Y", depart_hour=hour, flight_number=f"3{hour:02d}"
        )

    flight.status = FlightStatus.CANCELLED
    flight.save(update_fields=["status"])
    sweep()

    assert RebookOption.objects.count() == 3


def test_a_full_alternative_is_not_offered(client, make_flight, make_fare, celery_eager):
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y", depart_hour=6)
    make_fare(rbd="Y", amount="200.00")
    _book_and_pay(client, flight)

    full = make_flight(days_ahead=20, capacity=1, rbd="Y", depart_hour=9, flight_number="401")
    CabinConfig.objects.filter(flight=full).update(seats_sold=1)
    BookingClass.objects.filter(flight=full).update(sold=1)

    flight.status = FlightStatus.CANCELLED
    flight.save(update_fields=["status"])
    sweep()

    assert not RebookOption.objects.filter(proposed_flight=full).exists()


def test_the_booking_moves_to_disrupted_and_is_notified(disrupted, celery_eager):
    booking, _ = disrupted
    sweep()

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DISRUPTED
    assert OutboxEvent.objects.filter(
        aggregate_id=booking.pnr, event_type="flight_disrupted"
    ).exists()


def test_a_cancelled_booking_is_not_disturbed(client, make_flight, make_fare, celery_eager):
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")
    booking = _book_and_pay(client, flight)

    client.post(
        reverse("v1:booking-cancel", args=[booking.pnr]),
        {"last_name": "Islam"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    flight.status = FlightStatus.CANCELLED
    flight.save(update_fields=["status"])
    totals = sweep()

    assert totals["bookings_notified"] == 0
    assert not RebookOption.objects.exists()


def test_options_are_listed_for_the_passenger(client, disrupted, celery_eager):
    booking, _ = disrupted
    sweep()

    response = client.get(
        reverse("v1:rebook-option-list", args=[booking.pnr]), {"last_name": "Islam"}
    )

    assert response.status_code == 200
    assert len(response.data) >= 1
    assert response.data[0]["fare_delta"] == {"amount": "0.00", "currency": "USD"}
    assert response.data[0]["disruption_type"] == DisruptionType.CANCELLATION


def test_an_undisrupted_booking_has_no_options(client, make_flight, make_fare, celery_eager):
    flight = make_flight(days_ahead=20, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")
    booking = _book_and_pay(client, flight)

    response = client.get(
        reverse("v1:rebook-option-list", args=[booking.pnr]), {"last_name": "Islam"}
    )

    assert response.status_code == 200
    assert response.data == []


def test_a_stranger_cannot_read_the_options(client, disrupted, traveller, celery_eager):
    booking, _ = disrupted
    sweep()

    client.force_authenticate(traveller)
    response = client.get(reverse("v1:rebook-option-list", args=[booking.pnr]))

    assert response.status_code == 404


# --- acceptance --------------------------------------------------------------


def rebook(client, booking, option_id):
    return client.post(
        reverse("v1:booking-rebook", args=[booking.pnr]),
        {"option_id": str(option_id), "last_name": "Islam"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


def test_accepting_an_option_reissues_onto_the_new_flight(client, disrupted, celery_eager):
    booking, old_flight = disrupted
    sweep()
    option = RebookOption.objects.filter(booking=booking).order_by("rank").first()
    original = Ticket.objects.get()

    response = rebook(client, booking, option.public_id)

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.TICKETED

    original.refresh_from_db()
    assert original.status == TicketStatus.EXCHANGED
    assert list(original.coupons.values_list("status", flat=True)) == [CouponStatus.EXCHANGED]

    reissued = Ticket.objects.exclude(pk=original.pk).get()
    assert reissued.conjunction_of_id == original.pk
    assert reissued.coupons.first().segment.flight_id == option.proposed_flight_id

    # The new seat is sold and the old segment closed out.
    assert BookingClass.objects.get(flight=option.proposed_flight, rbd=option.rbd).sold == 1
    assert booking.segments.get(flight=old_flight).status == SegmentStatus.CANCELLED


def test_rebooking_costs_the_passenger_nothing(client, disrupted, celery_eager):
    booking, _ = disrupted
    sweep()
    option = RebookOption.objects.filter(booking=booking).first()
    paid_before = booking.paid_amount

    rebook(client, booking, option.public_id)

    booking.refresh_from_db()
    assert booking.paid_amount == paid_before
    assert booking.total_amount == paid_before
    assert booking.balance_due == 0


def test_taking_one_option_withdraws_the_others(client, disrupted, celery_eager):
    booking, _ = disrupted
    sweep()
    options = list(RebookOption.objects.filter(booking=booking).order_by("rank"))
    chosen = options[0]

    rebook(client, booking, chosen.public_id)

    chosen.refresh_from_db()
    assert chosen.status == RebookOptionStatus.ACCEPTED
    assert not RebookOption.objects.filter(
        booking=booking, status=RebookOptionStatus.OFFERED
    ).exists()


def test_an_expired_option_is_refused(client, disrupted, celery_eager):
    booking, _ = disrupted
    sweep()
    option = RebookOption.objects.filter(booking=booking).first()
    RebookOption.objects.filter(pk=option.pk).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )

    response = rebook(client, booking, option.public_id)

    assert response.status_code == 409
    booking.refresh_from_db()
    assert booking.status == BookingStatus.DISRUPTED


def test_an_option_whose_flight_filled_up_is_a_conflict(client, disrupted, celery_eager):
    """An option holds no inventory, so it can go stale between offer and acceptance."""
    booking, _ = disrupted
    sweep()
    option = RebookOption.objects.filter(booking=booking).order_by("rank").first()

    CabinConfig.objects.filter(flight=option.proposed_flight).update(seats_sold=10)
    BookingClass.objects.filter(flight=option.proposed_flight).update(sold=10)

    response = rebook(client, booking, option.public_id)

    assert response.status_code == 409
    assert response.data["code"] == "inventory_unavailable"


def test_rebooking_twice_is_refused(client, disrupted, celery_eager):
    booking, _ = disrupted
    sweep()
    options = list(RebookOption.objects.filter(booking=booking).order_by("rank"))

    rebook(client, booking, options[0].public_id)
    second = rebook(client, booking, options[0].public_id)

    assert second.status_code == 409
    assert Ticket.objects.filter(status=TicketStatus.ISSUED).count() == 1


def test_an_option_from_another_booking_is_not_found(
    client, disrupted, make_flight, make_fare, celery_eager
):
    booking, _ = disrupted
    sweep()

    other = make_flight(days_ahead=25, capacity=10, rbd="Y", flight_number="501")
    make_fare(rbd="Y", amount="200.00")
    other_booking = _book_and_pay(client, other)

    option = RebookOption.objects.filter(booking=booking).first()
    response = rebook(client, other_booking, option.public_id)

    assert response.status_code == 404


# --- ops view ----------------------------------------------------------------


def test_ops_sees_open_disruptions(client, disrupted, ops_agent, celery_eager):
    sweep()

    client.force_authenticate(ops_agent)
    response = client.get(reverse("v1:ops-disruption-list"))

    assert response.status_code == 200
    assert response.data[0]["type"] == DisruptionType.CANCELLATION


def test_the_disruption_list_is_closed_to_travellers(client, traveller):
    client.force_authenticate(traveller)
    assert client.get(reverse("v1:ops-disruption-list")).status_code == 403
