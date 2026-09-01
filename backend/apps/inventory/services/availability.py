from dataclasses import dataclass

from django.db import transaction
from django.db.models import F

from apps.common.exceptions import InventoryUnavailable

from ..constants import SELLABLE_FLIGHT_STATUSES
from ..models import BookingClass, CabinConfig, Flight


@dataclass(frozen=True, slots=True)
class SeatRequest:
    flight_id: int
    cabin: str
    rbd: str
    seats: int


@dataclass(frozen=True, slots=True)
class Availability:
    rbd: str
    seats_available: int
    sort_order: int


def cheapest_open_class(flight_id: int, cabin: str, seats: int) -> Availability | None:
    """Lowest-priced open RBD that can seat the party, respecting the cabin ceiling.

    Read-only and lock-free: results feed search, which must never block booking. The booking
    path re-checks the same numbers under ``select_for_update``.
    """
    cabin_config = (
        CabinConfig.objects.filter(flight_id=flight_id, cabin=cabin).only(
            "capacity", "seats_sold", "seats_held", "oversell_allowance"
        ).first()
    )
    if cabin_config is None or cabin_config.seats_available < seats:
        return None

    classes = (
        BookingClass.objects.filter(flight_id=flight_id, cabin_config=cabin_config, is_open=True)
        .annotate(free=F("authorised") - F("sold") - F("held"))
        .filter(free__gte=seats)
        .order_by("-sort_order")
    )
    best = classes.first()
    if best is None:
        return None
    return Availability(rbd=best.rbd, seats_available=best.seats_available,
                        sort_order=best.sort_order)


def _lock(requests: list[SeatRequest]) -> list[tuple[SeatRequest, CabinConfig, BookingClass]]:
    """Lock cabin + RBD rows in a single deterministic order: (flight_id, cabin, rbd).

    Every caller that touches more than one segment must acquire locks in this order. Two
    concurrent multi-segment bookings that lock in different orders deadlock.
    """
    ordered = sorted(requests, key=lambda r: (r.flight_id, r.cabin, r.rbd))
    locked = []

    for request in ordered:
        cabin_config = (
            CabinConfig.objects.select_for_update()
            .filter(flight_id=request.flight_id, cabin=request.cabin)
            .order_by("id")
            .first()
        )
        booking_class = (
            BookingClass.objects.select_for_update()
            .filter(flight_id=request.flight_id, rbd=request.rbd)
            .order_by("id")
            .first()
        )
        if cabin_config is None or booking_class is None:
            raise InventoryUnavailable(
                f"No {request.cabin}/{request.rbd} inventory on flight {request.flight_id}."
            )
        locked.append((request, cabin_config, booking_class))

    return locked


@transaction.atomic
def hold(requests: list[SeatRequest]) -> None:
    """Move seats into ``held``. Caller must already be inside the booking transaction."""
    sellable = set(
        Flight.objects.filter(
            id__in={r.flight_id for r in requests}, status__in=SELLABLE_FLIGHT_STATUSES
        ).values_list("id", flat=True)
    )

    for request, cabin_config, booking_class in _lock(requests):
        if request.flight_id not in sellable:
            raise InventoryUnavailable(f"Flight {request.flight_id} is not sellable.")

        if cabin_config.seats_available < request.seats:
            raise InventoryUnavailable(
                f"Only {cabin_config.seats_available} seat(s) left in {request.cabin} "
                f"on flight {request.flight_id}."
            )
        if not booking_class.is_open or booking_class.seats_available < request.seats:
            raise InventoryUnavailable(
                f"Class {request.rbd} has {booking_class.seats_available} seat(s) left "
                f"on flight {request.flight_id}."
            )

        # Plain arithmetic, not F(): the rows are already locked, and an F() expression would
        # leave the in-memory instance unusable for the caller.
        cabin_config.seats_held = cabin_config.seats_held + request.seats
        cabin_config.save(update_fields=["seats_held", "updated_at"])
        booking_class.held = booking_class.held + request.seats
        booking_class.save(update_fields=["held", "updated_at"])


@transaction.atomic
def release(requests: list[SeatRequest]) -> None:
    """Return held seats. Idempotent at the caller's level — never call twice for one hold."""
    for request, cabin_config, booking_class in _lock(requests):
        cabin_config.seats_held = max(0, cabin_config.seats_held - request.seats)
        cabin_config.save(update_fields=["seats_held", "updated_at"])
        booking_class.held = max(0, booking_class.held - request.seats)
        booking_class.save(update_fields=["held", "updated_at"])


@transaction.atomic
def confirm(requests: list[SeatRequest]) -> None:
    """Convert a hold into a sale: held decreases, sold increases, the total never moves."""
    for request, cabin_config, booking_class in _lock(requests):
        if cabin_config.seats_held < request.seats or booking_class.held < request.seats:
            raise InventoryUnavailable(
                f"Hold missing for flight {request.flight_id} {request.cabin}/{request.rbd}."
            )
        cabin_config.seats_held = max(0, cabin_config.seats_held - request.seats)
        cabin_config.seats_sold = cabin_config.seats_sold + request.seats
        cabin_config.save(update_fields=["seats_held", "seats_sold", "updated_at"])

        booking_class.held = max(0, booking_class.held - request.seats)
        booking_class.sold = booking_class.sold + request.seats
        booking_class.save(update_fields=["held", "sold", "updated_at"])


@transaction.atomic
def unsell(requests: list[SeatRequest]) -> None:
    """Reverse a confirmed sale — cancellation after ticketing, or a disruption rebook."""
    for request, cabin_config, booking_class in _lock(requests):
        cabin_config.seats_sold = max(0, cabin_config.seats_sold - request.seats)
        cabin_config.save(update_fields=["seats_sold", "updated_at"])
        booking_class.sold = max(0, booking_class.sold - request.seats)
        booking_class.save(update_fields=["sold", "updated_at"])
