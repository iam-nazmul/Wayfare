from decimal import Decimal

import pytest

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.common.exceptions import InvalidTransition
from apps.ticketing.constants import CouponStatus, TicketStatus
from apps.ticketing.models import Ticket, TicketSerial
from apps.ticketing.services.issue import issue_tickets
from apps.ticketing.services.numbers import (
    InvalidTicketNumber,
    check_digit,
    format_ticket_number,
    is_valid,
    next_ticket_number,
)

pytestmark = pytest.mark.django_db


def _booking(make_flight, passengers: list[tuple[str, str]]):
    from datetime import date

    from apps.booking.models import BookingSegment, Passenger

    flight = make_flight(days_ahead=30, capacity=10, rbd="Y")
    booking = Booking.objects.create(
        pnr=f"TK{Booking.objects.count():04d}",
        status=BookingStatus.PENDING_TICKETING,
        contact_email="t@example.com",
        base_amount=Decimal("200.00"),
        tax_amount=Decimal("30.00"),
        fee_amount=Decimal("10.00"),
        total_amount=Decimal("240.00"),
        paid_amount=Decimal("240.00"),
        currency="USD",
    )
    BookingSegment.objects.create(
        booking=booking,
        flight=flight,
        sequence=0,
        cabin="ECONOMY",
        rbd="Y",
        marketing_flight_number=flight.designator,
    )
    for pax_type, last_name in passengers:
        Passenger.objects.create(
            booking=booking,
            type=pax_type,
            first_name="Test",
            last_name=last_name,
            dob=date(1990, 5, 14),
        )
    return booking


@pytest.fixture
def client_booking(make_flight):
    return _booking(make_flight, [("ADT", "Islam")])


@pytest.fixture
def client_booking_family(make_flight):
    return _booking(make_flight, [("ADT", "Islam"), ("ADT", "Rahman"), ("CHD", "Islam")])


def test_the_check_digit_is_the_body_modulo_seven():
    assert check_digit("176", 1) == int("176000000001") % 7
    assert is_valid(format_ticket_number("176", 1))


def test_a_ticket_number_is_thirteen_digits():
    number = format_ticket_number("176", 42)
    assert len(number) == 13
    assert number.startswith("176")
    assert is_valid(number)


def test_a_corrupted_ticket_number_fails_validation():
    number = format_ticket_number("176", 42)
    wrong = number[:12] + str((int(number[12]) + 1) % 7)
    assert not is_valid(wrong)


def test_serials_do_not_repeat_for_an_airline():
    numbers = {next_ticket_number("176") for _ in range(25)}
    assert len(numbers) == 25
    assert all(is_valid(number) for number in numbers)
    assert TicketSerial.objects.get(airline_prefix="176").last_serial == 25


def test_each_airline_has_its_own_series():
    next_ticket_number("176")
    next_ticket_number("125")

    assert TicketSerial.objects.get(airline_prefix="176").last_serial == 1
    assert TicketSerial.objects.get(airline_prefix="125").last_serial == 1


def test_a_prefix_that_is_not_three_digits_is_refused():
    with pytest.raises(InvalidTicketNumber):
        next_ticket_number("WF")


def test_only_a_paid_booking_can_be_ticketed(db):
    booking = Booking.objects.create(
        pnr="TKT001", status=BookingStatus.HELD, contact_email="t@example.com"
    )

    with pytest.raises(InvalidTransition):
        issue_tickets(booking)

    assert not Ticket.objects.exists()


def test_issuing_twice_returns_the_same_tickets(client_booking):
    first = issue_tickets(client_booking)
    second = issue_tickets(client_booking)

    assert [ticket.pk for ticket in first] == [ticket.pk for ticket in second]
    assert Ticket.objects.count() == len(first)


def test_issuing_creates_open_coupons_and_ticketed_booking(client_booking):
    tickets = issue_tickets(client_booking)

    ticket = tickets[0]
    assert ticket.status == TicketStatus.ISSUED
    assert list(ticket.coupons.values_list("status", flat=True)) == [CouponStatus.OPEN]
    assert ticket.coupons.first().coupon_number == 1
    assert ticket.fare_calculation

    client_booking.refresh_from_db()
    assert client_booking.status == BookingStatus.TICKETED


def test_every_passenger_gets_their_own_ticket(client_booking_family):
    tickets = issue_tickets(client_booking_family)

    assert len(tickets) == client_booking_family.passengers.count()
    assert len({ticket.ticket_number for ticket in tickets}) == len(tickets)


def test_the_tickets_sum_to_the_booking_total(client_booking_family):
    tickets = issue_tickets(client_booking_family)

    total = sum(ticket.total_amount for ticket in tickets)
    expected = (
        client_booking_family.base_amount
        + client_booking_family.tax_amount
        + client_booking_family.fee_amount
    )
    assert total == expected
