from django.db import transaction

from ..models import TicketSerial

SERIAL_DIGITS = 9
MAX_SERIAL = 10**SERIAL_DIGITS - 1


class InvalidTicketNumber(ValueError):
    pass


def check_digit(prefix: str, serial: int) -> int:
    """IATA check digit: the 12-digit body modulo 7 (SPEC.md §5.6)."""
    return int(f"{prefix}{serial:0{SERIAL_DIGITS}d}") % 7


def format_ticket_number(prefix: str, serial: int) -> str:
    return f"{prefix}{serial:0{SERIAL_DIGITS}d}{check_digit(prefix, serial)}"


def is_valid(ticket_number: str) -> bool:
    if len(ticket_number) != 13 or not ticket_number.isdigit():
        return False
    body, digit = ticket_number[:12], int(ticket_number[12])
    return int(body) % 7 == digit


def next_ticket_number(airline_prefix: str) -> str:
    """Draw the next serial for an airline.

    SPEC.md §5.6 calls for a Postgres sequence per airline; a sequence name cannot be a bound
    parameter, so that means interpolating DDL on every issue (invariant 10). A counter row
    locked with ``select_for_update`` gives the same monotonic per-airline serial with no
    dynamic SQL — two ticketing workers serialise on the row instead of racing.
    """
    if not (airline_prefix.isdigit() and len(airline_prefix) == 3):
        raise InvalidTicketNumber(f"{airline_prefix!r} is not a 3-digit ticketing prefix.")

    with transaction.atomic():
        counter, _ = TicketSerial.objects.select_for_update().get_or_create(
            airline_prefix=airline_prefix
        )
        counter.last_serial = counter.last_serial + 1 if counter.last_serial < MAX_SERIAL else 1
        counter.save(update_fields=["last_serial", "updated_at"])
        serial = counter.last_serial

    return format_ticket_number(airline_prefix, serial)
