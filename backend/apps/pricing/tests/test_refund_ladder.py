from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.pricing.services.refunds import (
    NO_SHOW_PENALTY,
    penalty_rate,
    quote_refund,
)

pytestmark = pytest.mark.django_db

NOW = timezone.now()


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (timedelta(days=30), Decimal("0.00")),
        # Exactly on a boundary stays in the cheaper band — SPEC.md §14.6.
        (timedelta(days=7), Decimal("0.00")),
        (timedelta(days=7) - timedelta(seconds=1), Decimal("0.25")),
        (timedelta(days=2), Decimal("0.25")),
        (timedelta(days=1), Decimal("0.25")),
        (timedelta(hours=23), Decimal("0.50")),
        (timedelta(minutes=1), Decimal("0.50")),
        (timedelta(seconds=-1), NO_SHOW_PENALTY),
    ],
)
def test_the_ladder_steps_at_each_boundary(remaining, expected):
    assert penalty_rate(NOW + remaining, now=NOW) == expected


def _booking(make_flight, make_fare, fare_family, *, days_ahead, refundable, paid="260.50"):
    from apps.booking.constants import BookingStatus
    from apps.booking.models import Booking, BookingSegment

    fare_family.refundable = refundable
    fare_family.refund_fee = Decimal("40.00") if refundable else Decimal("0.00")
    fare_family.save()

    flight = make_flight(days_ahead=days_ahead, capacity=10, rbd="Y")
    booking = Booking.objects.create(
        pnr=f"RF{Booking.objects.count():04d}",
        status=BookingStatus.TICKETED,
        contact_email="t@example.com",
        base_amount=Decimal("210.00"),
        tax_amount=Decimal("41.00"),
        fee_amount=Decimal("9.50"),
        total_amount=Decimal("260.50"),
        paid_amount=Decimal(paid),
        currency="USD",
        price_breakdown={
            "tax_lines": [
                {"code": "YQ", "amount": {"amount": "18.00", "currency": "USD"},
                 "refundable": False},
                {"code": "XT", "amount": {"amount": "12.50", "currency": "USD"},
                 "refundable": False},
                {"code": "VAT", "amount": {"amount": "10.50", "currency": "USD"},
                 "refundable": True},
            ]
        },
    )
    BookingSegment.objects.create(
        booking=booking, flight=flight, sequence=0, cabin="ECONOMY", rbd="Y",
        fare_family=fare_family, marketing_flight_number=flight.designator,
    )
    return booking


def test_a_refundable_fare_keeps_the_fee_and_non_refundable_taxes(
    make_flight, make_fare, fare_family
):
    booking = _booking(make_flight, make_fare, fare_family, days_ahead=30, refundable=True)

    quote = quote_refund(booking)

    # 30 days out: no fare penalty, just the 40.00 refund fee.
    assert quote.penalty.amount == Decimal("40.00")
    # YQ 18.00 + XT 12.50 withheld, plus the 9.50 booking fee.
    assert quote.non_refundable_tax.amount == Decimal("40.00")
    assert quote.refundable.amount == Decimal("180.50")
    assert quote.refundable_fare is True


def test_the_fare_penalty_applies_inside_the_ladder(make_flight, make_fare, fare_family):
    booking = _booking(make_flight, make_fare, fare_family, days_ahead=2, refundable=True)

    quote = quote_refund(booking)

    # 25% of the 210.00 base, plus the fee.
    assert quote.penalty.amount == Decimal("92.50")
    assert quote.refundable.amount == Decimal("128.00")


def test_a_non_refundable_fare_returns_only_refundable_taxes(
    make_flight, make_fare, fare_family
):
    booking = _booking(make_flight, make_fare, fare_family, days_ahead=30, refundable=False)

    quote = quote_refund(booking)

    assert quote.refundable_fare is False
    # Base forfeit, YQ/XT/fee withheld: only the refundable VAT comes back.
    assert quote.penalty.amount == Decimal("210.00")
    assert quote.refundable.amount == Decimal("10.50")


def test_nothing_paid_means_nothing_to_refund(make_flight, make_fare, fare_family):
    booking = _booking(
        make_flight, make_fare, fare_family, days_ahead=30, refundable=True, paid="0.00"
    )

    quote = quote_refund(booking)

    assert quote.refundable.amount == Decimal("0.00")
    assert "Nothing has been paid" in quote.reason


def test_the_refund_never_goes_negative(make_flight, make_fare, fare_family):
    booking = _booking(
        make_flight, make_fare, fare_family, days_ahead=0, refundable=False, paid="20.00"
    )

    quote = quote_refund(booking)

    assert quote.refundable.amount >= Decimal("0.00")
    assert quote.penalty.amount <= quote.paid.amount
