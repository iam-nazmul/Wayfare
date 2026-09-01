from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.pricing.constants import CalcType, PassengerType, TaxScope
from apps.pricing.models import Fare, FeeRule, TaxRule
from apps.pricing.services.quote import (
    NoFareFound,
    PassengerCount,
    find_fare,
    passenger_type_for,
    quote_itinerary,
)

pytestmark = pytest.mark.django_db


class TestPassengerType:
    """Age is evaluated at the RETURN date — the rule that stops a denied boarding home."""

    def test_infant_under_two(self):
        assert passenger_type_for(date(2025, 6, 1), date(2026, 9, 1)) == PassengerType.INFANT

    def test_child_from_second_birthday(self):
        assert passenger_type_for(date(2024, 9, 1), date(2026, 9, 1)) == PassengerType.CHILD

    def test_adult_from_twelfth_birthday(self):
        assert passenger_type_for(date(2014, 9, 1), date(2026, 9, 1)) == PassengerType.ADULT

    def test_child_turning_twelve_before_return_is_an_adult(self):
        dob = date(2014, 9, 20)
        assert passenger_type_for(dob, date(2026, 9, 10)) == PassengerType.CHILD
        assert passenger_type_for(dob, date(2026, 9, 25)) == PassengerType.ADULT

    def test_missing_dob_defaults_to_adult(self):
        assert passenger_type_for(None, date(2026, 9, 1)) == PassengerType.ADULT


class TestFareRules:
    def test_advance_purchase_gate_at_the_boundary(self, make_flight, make_fare):
        """Exactly meeting the requirement qualifies; one day short does not."""
        flight = make_flight(days_ahead=5)
        departure = flight.departure_utc.date()
        gap = (departure - date.today()).days

        make_fare(rbd="Y", advance_purchase_days=gap)
        assert find_fare(flight, "ECONOMY", "Y", departure=departure) is not None

        Fare.objects.update(advance_purchase_days=gap + 1)
        assert find_fare(flight, "ECONOMY", "Y", departure=departure) is None

    def test_minimum_stay_gate(self, make_flight, make_fare):
        flight = make_flight(days_ahead=7)
        make_fare(rbd="Y", min_stay_days=6)
        departure = flight.departure_utc.date()

        assert find_fare(
            flight, "ECONOMY", "Y", departure=departure, return_date=departure + timedelta(days=6)
        ) is not None
        assert find_fare(
            flight, "ECONOMY", "Y", departure=departure, return_date=departure + timedelta(days=3)
        ) is None

    def test_maximum_stay_gate(self, make_flight, make_fare):
        flight = make_flight(days_ahead=7)
        make_fare(rbd="Y", max_stay_days=10)
        departure = flight.departure_utc.date()

        assert find_fare(
            flight, "ECONOMY", "Y", departure=departure, return_date=departure + timedelta(days=9)
        ) is not None
        assert find_fare(
            flight, "ECONOMY", "Y", departure=departure, return_date=departure + timedelta(days=30)
        ) is None

    def test_typed_child_fare_beats_a_discounted_adult_fare(self, make_flight, make_fare):
        flight = make_flight()
        make_fare(rbd="Y", amount="200.00", passenger_type=PassengerType.ADULT)
        make_fare(rbd="Y", amount="120.00", passenger_type=PassengerType.CHILD)

        fare = find_fare(
            flight, "ECONOMY", "Y", departure=flight.departure_utc.date(),
            passenger_type=PassengerType.CHILD,
        )
        assert fare.base_amount == Decimal("120.00")


class TestQuote:
    def test_party_pricing_applies_the_child_discount(self, make_flight, make_fare):
        flight = make_flight()
        make_fare(rbd="Y", amount="200.00")

        breakdown = quote_itinerary(
            [(flight, "ECONOMY", "Y")], PassengerCount(adults=2, children=1)
        )
        # 2 adults at 200 + 1 child at 75% of 200
        assert breakdown.base_amount.amount == Decimal("550.00")

    def test_infant_pays_a_token_fare(self, make_flight, make_fare):
        flight = make_flight()
        make_fare(rbd="Y", amount="200.00")

        breakdown = quote_itinerary(
            [(flight, "ECONOMY", "Y")], PassengerCount(adults=1, infants=1)
        )
        assert breakdown.base_amount.amount == Decimal("220.00")

    def test_missing_fare_raises(self, make_flight):
        flight = make_flight()
        with pytest.raises(NoFareFound):
            quote_itinerary([(flight, "ECONOMY", "Y")], PassengerCount(adults=1))

    def test_total_is_base_plus_tax_plus_fee_minus_discount(self, make_flight, make_fare):
        flight = make_flight()
        make_fare(rbd="Y", amount="100.00")
        TaxRule.objects.create(
            code="YQ", name="Surcharge", applies_to=TaxScope.SEGMENT,
            calc_type=CalcType.FIXED, value=Decimal("10.00"),
        )
        FeeRule.objects.create(
            code="OB", name="Booking fee", scope="BOOKING",
            calc_type=CalcType.FIXED, value=Decimal("5.00"),
        )

        breakdown = quote_itinerary([(flight, "ECONOMY", "Y")], PassengerCount(adults=2))

        assert breakdown.base_amount.amount == Decimal("200.00")
        assert breakdown.tax_amount.amount == Decimal("20.00")   # per segment, per passenger
        assert breakdown.fee_amount.amount == Decimal("5.00")    # once per booking
        assert breakdown.total.amount == Decimal("225.00")

    def test_percent_tax_is_calculated_on_the_base(self, make_flight, make_fare):
        flight = make_flight()
        make_fare(rbd="Y", amount="100.00")
        TaxRule.objects.create(
            code="VAT", name="VAT", applies_to=TaxScope.ITINERARY,
            calc_type=CalcType.PERCENT, value=Decimal("5.00"), is_refundable=True,
        )

        breakdown = quote_itinerary([(flight, "ECONOMY", "Y")], PassengerCount(adults=1))
        assert breakdown.tax_amount.amount == Decimal("5.00")
        assert breakdown.taxes[0]["refundable"] is True


class TestPassengerCount:
    def test_infants_do_not_consume_seat_inventory(self):
        assert PassengerCount(adults=2, children=1, infants=2).seated == 3
        assert PassengerCount(adults=2, children=1, infants=2).total == 5
