import json
import logging
from datetime import UTC, datetime

from celery import shared_task
from django.conf import settings

from .clickhouse import insert_rows
from .events import stream_client

logger = logging.getLogger("wayfare.analytics")

GROUP = "wayfare-analytics"
CONSUMER = "worker-1"
BATCH = 5_000

CLICKSTREAM_COLUMNS = [
    "event_id", "event_time", "event_name", "session_id", "anon_id", "user_id",
    "page_path", "referrer", "device_type", "origin", "destination", "cabin",
    "pax_count", "amount", "currency", "duration_ms", "props",
]

REQUEST_LOG_COLUMNS = [
    "request_id", "ts", "method", "path", "route", "status",
    "duration_ms", "user_id", "ip", "user_agent", "error_code",
]

SEARCH_LOG_COLUMNS = [
    "search_id", "event_time", "session_id", "user_id", "origin", "destination",
    "depart_date", "return_date", "trip_type", "pax_adults", "pax_children",
    "pax_infants", "cabin", "currency", "results_count", "cheapest_amount",
    "median_amount", "cache_hit", "latency_ms", "partial",
]


def _ensure_group() -> None:
    client = stream_client()
    try:
        client.xgroup_create(settings.EVENT_STREAM_KEY, GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


@shared_task(name="analytics.flush_event_buffer", queue="analytics", acks_late=True)
def flush_event_buffer() -> int:
    """Drain the Redis Stream into ClickHouse.

    At-least-once: entries are acked only after a successful insert, so a crash re-delivers
    rather than drops. Every table dedups on event_id.
    """
    _ensure_group()
    client = stream_client()

    entries = client.xreadgroup(
        GROUP, CONSUMER, {settings.EVENT_STREAM_KEY: ">"}, count=BATCH, block=1000
    )
    if not entries:
        return 0

    clickstream: list[list] = []
    requests: list[list] = []
    searches: list[list] = []
    ack_ids: list[str] = []

    for _stream, messages in entries:
        for entry_id, fields in messages:
            ack_ids.append(entry_id)
            kind = fields.get("kind")
            payload = json.loads(fields.get("payload", "{}"))
            if kind == "clickstream":
                clickstream.append(_clickstream_row(payload))
            elif kind == "api_request":
                requests.append(_request_row(payload))
            elif kind == "search":
                searches.append(_search_row(payload))

    try:
        insert_rows("wayfare.events", clickstream, CLICKSTREAM_COLUMNS)
        insert_rows("wayfare.api_request_log", requests, REQUEST_LOG_COLUMNS)
        insert_rows("wayfare.search_log", searches, SEARCH_LOG_COLUMNS)
    except Exception:
        logger.warning("clickhouse_insert_failed", exc_info=True)
        return 0  # leave the entries unacked; the next tick retries them

    if ack_ids:
        client.xack(settings.EVENT_STREAM_KEY, GROUP, *ack_ids)
    return len(ack_ids)


def _clickstream_row(payload: dict) -> list:
    from apps.common.uuid7 import uuid7

    props = payload.get("props") or {}
    return [
        uuid7(),
        _ts(payload.get("event_time")),
        payload.get("event_name", ""),
        payload.get("session_id", ""),
        payload.get("anon_id", ""),
        payload.get("user_id"),
        payload.get("page_path", ""),
        payload.get("referrer", ""),
        payload.get("device_type", ""),
        props.get("origin", ""),
        props.get("destination", ""),
        props.get("cabin", ""),
        int(props.get("pax_count", 0) or 0),
        props.get("amount", 0) or 0,
        props.get("currency", ""),
        int(props.get("duration_ms", 0) or 0),
        json.dumps(props, default=str),
    ]


def _request_row(payload: dict) -> list:
    return [
        payload.get("request_id", ""),
        _ts(payload.get("ts")),
        payload.get("method", ""),
        payload.get("path", "")[:512],
        payload.get("route", "")[:256],
        int(payload.get("status", 0)),
        int(payload.get("duration_ms", 0)),
        payload.get("user_id"),
        payload.get("ip") or "::",
        payload.get("user_agent", "")[:512],
        payload.get("error_code", ""),
    ]


def _search_row(payload: dict) -> list:
    from datetime import date as date_type

    def as_date(value):
        return date_type.fromisoformat(value) if value else None

    return [
        payload.get("search_id"),
        _ts(payload.get("event_time")),
        payload.get("session_id", ""),
        payload.get("user_id"),
        payload.get("origin", ""),
        payload.get("destination", ""),
        as_date(payload.get("depart_date")),
        as_date(payload.get("return_date")),
        payload.get("trip_type", ""),
        int(payload.get("pax_adults", 0)),
        int(payload.get("pax_children", 0)),
        int(payload.get("pax_infants", 0)),
        payload.get("cabin", ""),
        payload.get("currency", ""),
        int(payload.get("results_count", 0)),
        payload.get("cheapest_amount", "0"),
        payload.get("median_amount", "0"),
        int(payload.get("cache_hit", 0)),
        int(payload.get("latency_ms", 0)),
        int(payload.get("partial", 0)),
    ]


def _ts(value) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


MIRROR_COLUMNS = [
    "booking_id", "pnr", "status", "user_id", "agency_id", "origin", "destination",
    "trip_type", "cabin", "pax_count", "base_amount", "tax_amount", "ancillary_amount",
    "total_amount", "total_amount_usd", "currency", "source_channel",
    "booked_at", "departure_at", "updated_at",
]

FARE_HISTORY_COLUMNS = [
    "captured_at", "origin", "destination", "depart_date", "cabin",
    "cheapest_amount", "currency", "seats_remaining",
]

#: Where the incremental cursor lives between runs. Losing it re-mirrors, which is harmless:
#: `bookings_mirror` is a ReplacingMergeTree keyed on booking_id.
MIRROR_CURSOR_KEY = "wf:analytics:mirror_cursor"


@shared_task(name="analytics.sync_bookings_to_clickhouse", queue="analytics", acks_late=True)
def sync_bookings_to_clickhouse(full: bool = False, batch: int = 5_000) -> int:
    """Mirror Postgres bookings into ClickHouse, incrementally by ``updated_at``.

    Postgres stays the system of record; the mirror exists so revenue reporting never joins
    against the booking path (CLAUDE.md invariant 1). Re-running is safe — the target is a
    ReplacingMergeTree keyed on ``booking_id``, so a row seen twice collapses.
    """
    from django.core.cache import cache

    from apps.booking.models import Booking

    since = None if full else cache.get(MIRROR_CURSOR_KEY)

    queryset = Booking.objects.select_related("agency").prefetch_related(
        "segments__flight", "passengers"
    )
    if since is not None:
        queryset = queryset.filter(updated_at__gt=since)

    bookings = list(queryset.order_by("updated_at")[:batch])
    if not bookings:
        return 0

    rows = [_mirror_row(booking) for booking in bookings]

    try:
        insert_rows("wayfare.bookings_mirror", rows, MIRROR_COLUMNS)
    except Exception:
        logger.warning("mirror_sync_failed", exc_info=True)
        return 0

    # Advanced only after a successful insert, so a failure re-sends rather than skips.
    cache.set(MIRROR_CURSOR_KEY, bookings[-1].updated_at, None)
    logger.info("bookings_mirrored", extra={"count": len(rows)})
    return len(rows)


def _mirror_row(booking) -> list:
    from apps.pricing.constants import PassengerType

    segments = list(booking.segments.all())
    first = segments[0] if segments else None
    last = segments[-1] if segments else None

    return [
        booking.id,
        booking.pnr,
        booking.status,
        booking.user_id,
        booking.agency_id,
        first.flight.origin_airport_id if first else "",
        last.flight.destination_airport_id if last else "",
        booking.trip_type,
        first.cabin if first else "",
        sum(1 for p in booking.passengers.all() if p.type != PassengerType.INFANT),
        booking.base_amount,
        booking.tax_amount,
        booking.ancillary_amount,
        booking.total_amount,
        _usd(booking.total_amount, booking.currency),
        booking.currency,
        booking.source_channel,
        booking.booked_at or booking.created_at,
        first.flight.departure_utc if first else booking.created_at,
        booking.updated_at,
    ]


def _usd(amount, currency: str):
    """Normalise for cross-currency revenue reporting, at today's rate.

    A booking sold in BDT and reported in USD is converted once, here — the report must not do
    arithmetic across currencies itself.
    """
    from decimal import Decimal

    if currency == "USD":
        return amount

    from apps.catalog.selectors import latest_rate

    rate = latest_rate(currency, "USD")
    return (Decimal(amount) * Decimal(rate.rate)).quantize(Decimal("0.01")) if rate else amount


@shared_task(name="analytics.rollup_daily_metrics", queue="analytics", acks_late=True)
def rollup_daily_metrics(day: str | None = None) -> int:
    """Snapshot the day's cheapest priced fare per route, date and cabin.

    The materialised views cover everything derivable from the event stream; this is the piece
    that needs a Postgres join, and it is what the fare-trend report reads.
    """
    from datetime import date as date_type

    from django.db.models import Min

    from apps.booking.models import Offer

    target = date_type.fromisoformat(day) if day else datetime.now(UTC).date()

    rows = (
        Offer.objects.filter(created_at__date=target)
        .values(
            "search_query__origin",
            "search_query__destination",
            "search_query__depart_date",
            "search_query__cabin",
            "currency",
        )
        .annotate(cheapest=Min("total_amount"), seats=Min("seats_remaining"))
        .order_by()
    )

    captured = datetime.now(UTC).replace(microsecond=0)
    payload = [
        [
            captured,
            row["search_query__origin"],
            row["search_query__destination"],
            row["search_query__depart_date"],
            row["search_query__cabin"],
            row["cheapest"],
            row["currency"],
            min(int(row["seats"] or 0), 65535),
        ]
        for row in rows
        if row["search_query__depart_date"]
    ]

    if not payload:
        return 0

    try:
        insert_rows("wayfare.fare_price_history", payload, FARE_HISTORY_COLUMNS)
    except Exception:
        logger.warning("fare_history_insert_failed", exc_info=True)
        return 0

    logger.info("fare_prices_captured", extra={"rows": len(payload), "day": str(target)})
    return len(payload)
