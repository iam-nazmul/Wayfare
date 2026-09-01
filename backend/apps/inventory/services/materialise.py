import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..constants import DEFAULT_RBDS, Cabin, ScheduleStatus
from ..models import (
    BookingClass,
    CabinConfig,
    Flight,
    FlightSchedule,
    ScheduleMaterialisation,
    Seat,
)

logger = logging.getLogger("wayfare.inventory")


def materialise_schedule(schedule: FlightSchedule, start: date, end: date) -> tuple[int, int]:
    """Turn one schedule into dated flights across [start, end].

    Local departure time is authored once; each date is converted through the origin airport's
    zone, so a DST boundary moves the UTC departure without touching the printed local time.
    """
    created = skipped = 0
    origin_tz = ZoneInfo(schedule.route.origin_airport.timezone)
    dest_tz = ZoneInfo(schedule.route.destination_airport.timezone)

    day = max(start, schedule.effective_from)
    last = min(end, schedule.effective_to)

    while day <= last:
        if not schedule.operates_on(day.weekday()):
            day += timedelta(days=1)
            continue

        wall_departure = datetime.combine(day, schedule.dep_time_local)
        wall_arrival = datetime.combine(
            day + timedelta(days=schedule.arrival_day_offset), schedule.arr_time_local
        )

        departure_utc = wall_departure.replace(tzinfo=origin_tz).astimezone(UTC)
        arrival_utc = wall_arrival.replace(tzinfo=dest_tz).astimezone(UTC)
        duration = int((arrival_utc - departure_utc).total_seconds() // 60)

        # *_local carries the airport wall clock — what the boarding pass prints. Django's
        # DateTimeField cannot hold a naive value under USE_TZ, so the wall clock is stored in a
        # UTC container: the digits are the local time and must never be timezone-converted.
        departure_local = wall_departure.replace(tzinfo=UTC)
        arrival_local = wall_arrival.replace(tzinfo=UTC)

        if duration <= 0:
            logger.warning(
                "schedule_negative_duration",
                extra={"schedule_id": schedule.id, "date": str(day)},
            )
            skipped += 1
            day += timedelta(days=1)
            continue

        try:
            with transaction.atomic():
                flight = Flight.objects.create(
                    schedule=schedule,
                    airline=schedule.airline,
                    flight_number=schedule.flight_number,
                    origin_airport=schedule.route.origin_airport,
                    destination_airport=schedule.route.destination_airport,
                    aircraft=schedule.aircraft,
                    seat_map_template=schedule.seat_map_template,
                    departure_utc=departure_utc,
                    arrival_utc=arrival_utc,
                    departure_local=departure_local,
                    arrival_local=arrival_local,
                    duration_minutes=duration,
                )
                build_inventory(flight, schedule.default_cabin_capacity)
                build_seats(flight)
            created += 1
        except IntegrityError:
            # uniq_flight_departure — this date was already materialised.
            skipped += 1

        day += timedelta(days=1)

    ScheduleMaterialisation.objects.create(
        schedule=schedule,
        window_start=start,
        window_end=end,
        flights_created=created,
        flights_skipped=skipped,
    )
    return created, skipped


def build_inventory(flight: Flight, capacities: dict[str, int]) -> None:
    """Create cabin capacity and the RBD ladder beneath it.

    Authorisations start at full cabin capacity for every bucket: nested inventory, so the sum
    across RBDs deliberately exceeds the cabin. The cabin row is the ceiling.
    """
    for cabin, capacity in (capacities or {Cabin.ECONOMY: 180}).items():
        cabin_config = CabinConfig.objects.create(
            flight=flight, cabin=cabin, capacity=int(capacity)
        )
        for order, rbd in enumerate(DEFAULT_RBDS.get(cabin, [])):
            BookingClass.objects.create(
                flight=flight,
                cabin_config=cabin_config,
                rbd=rbd,
                authorised=int(capacity),
                sort_order=order,
            )


def build_seats(flight: Flight) -> None:
    layout = flight.seat_map_template.layout or {}
    seats: list[Seat] = []

    for block in layout.get("cabins", []):
        cabin = block.get("cabin", Cabin.ECONOMY)
        row_from, row_to = block.get("rows", [1, 30])
        columns = block.get("columns", "ABC DEF")
        exit_rows = set(block.get("exit_rows", []))
        fee = block.get("seat_fee", 0)

        letters = [c for c in columns if c != " "]
        for row in range(row_from, row_to + 1):
            for column in letters:
                seats.append(
                    Seat(
                        flight=flight,
                        cabin=cabin,
                        row=row,
                        column=column,
                        seat_number=f"{row}{column}",
                        characteristics=_characteristics(column, columns, row in exit_rows),
                        is_exit_row=row in exit_rows,
                        seat_fee_amount=fee,
                        seat_fee_currency=block.get("currency", "USD"),
                    )
                )

    Seat.objects.bulk_create(seats, batch_size=500, ignore_conflicts=True)


def _characteristics(column: str, columns: str, is_exit: bool) -> list[str]:
    """Classify a seat from the cabin layout string, e.g. "ABC DEF" or "AB DE FG".

    Groups are separated by aisles. The outermost edge of the first and last group is a window;
    any other group edge borders an aisle; everything else is a middle seat.
    """
    groups = columns.split(" ")
    result: list[str] = []

    for position, group in enumerate(groups):
        if column not in group:
            continue
        index = group.index(column)
        at_start, at_end = index == 0, index == len(group) - 1
        is_window = (position == 0 and at_start) or (position == len(groups) - 1 and at_end)

        if is_window:
            result.append("WINDOW")
        elif at_start or at_end:
            result.append("AISLE")
        else:
            result.append("MIDDLE")
        break

    if is_exit:
        result.append("EXTRA_LEGROOM")
    return result


def materialise_all(days: int = 365) -> dict[str, int]:
    start = timezone.now().date()
    end = start + timedelta(days=days)
    totals = {"created": 0, "skipped": 0, "schedules": 0}

    schedules = FlightSchedule.objects.filter(
        status=ScheduleStatus.ACTIVE, effective_to__gte=start
    ).select_related("route__origin_airport", "route__destination_airport", "airline",
                     "aircraft", "seat_map_template")

    for schedule in schedules:
        created, skipped = materialise_schedule(schedule, start, end)
        totals["created"] += created
        totals["skipped"] += skipped
        totals["schedules"] += 1

    return totals
