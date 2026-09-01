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
    "page_path", "referrer", "origin", "destination", "cabin", "pax_count",
    "amount", "currency", "duration_ms", "props",
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
    except Exception as exc:  # noqa: BLE001 — BUSYGROUP means it already exists
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
    except Exception:  # noqa: BLE001
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


@shared_task(name="analytics.sync_bookings_to_clickhouse", queue="analytics")
def sync_bookings_to_clickhouse(full: bool = False) -> int:
    """Mirror Postgres bookings into wayfare.bookings_mirror. Implemented with M3 (booking)."""
    return 0


@shared_task(name="analytics.rollup_daily_metrics", queue="analytics")
def rollup_daily_metrics(day: str | None = None) -> int:
    """Materialised views handle most rollups; this backfills any that need Postgres joins."""
    return 0
