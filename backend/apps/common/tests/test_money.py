from decimal import Decimal

import pytest

from apps.common.money import CurrencyMismatch, Money, total


def test_quantizes_to_two_places():
    assert Money(Decimal("10.005"), "USD").amount == Decimal("10.01")
    assert Money(Decimal("10.004"), "USD").amount == Decimal("10.00")


def test_coerces_strings_and_uppercases_currency():
    money = Money("12.5", "usd")
    assert money.amount == Decimal("12.50")
    assert money.currency == "USD"


def test_addition_and_subtraction():
    assert (Money(Decimal("10"), "USD") + Money(Decimal("5.50"), "USD")).amount == Decimal("15.50")
    assert (Money(Decimal("10"), "USD") - Money(Decimal("2.25"), "USD")).amount == Decimal("7.75")


def test_multiplication_by_a_count():
    assert (Money(Decimal("19.99"), "USD") * 3).amount == Decimal("59.97")


def test_child_discount_rounds_half_up():
    assert (Money(Decimal("200.00"), "USD") * Decimal("0.75")).amount == Decimal("150.00")
    assert (Money(Decimal("199.99"), "USD") * Decimal("0.75")).amount == Decimal("149.99")


def test_mixing_currencies_is_refused():
    with pytest.raises(CurrencyMismatch):
        Money(Decimal("10"), "USD") + Money(Decimal("10"), "EUR")

    with pytest.raises(CurrencyMismatch):
        Money(Decimal("10"), "USD") < Money(Decimal("10"), "EUR")


def test_minor_units_round_trip():
    assert Money(Decimal("412.50"), "USD").minor_units == 41250
    assert Money.from_minor_units(41250, "USD").amount == Decimal("412.50")


def test_zero_and_is_zero():
    assert Money.zero("USD").is_zero is True
    assert Money(Decimal("0.01"), "USD").is_zero is False


def test_as_dict_is_the_wire_format():
    assert Money(Decimal("412.5"), "USD").as_dict() == {"amount": "412.50", "currency": "USD"}


def test_total_sums_a_list():
    amounts = [Money(Decimal("10"), "USD"), Money(Decimal("5"), "USD")]
    assert total(amounts, "USD").amount == Decimal("15.00")
    assert total([], "USD").is_zero


def test_money_is_immutable():
    money = Money(Decimal("10"), "USD")
    with pytest.raises((AttributeError, TypeError)):
        money.amount = Decimal("20")  # type: ignore[misc]
