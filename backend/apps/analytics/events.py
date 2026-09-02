import json
import logging
from typing import Any

import redis
from django.conf import settings

logger = logging.getLogger("wayfare.analytics")

_stream: redis.Redis | None = None


def stream_client() -> redis.Redis:
    global _stream
    if _stream is None:
        _stream = redis.Redis.from_url(settings.REDIS_EVENTS_URL, decode_responses=True)
    return _stream


def enabled() -> bool:
    return getattr(settings, "ANALYTICS_ENABLED", True)


def push(kind: str, payload: dict[str, Any]) -> None:
    """Buffer one event for the analytics worker.

    Never raises: a broken analytics path must not fail a booking (SPEC.md §9.1).
    """
    if not enabled():
        return
    try:
        stream_client().xadd(
            settings.EVENT_STREAM_KEY,
            {"kind": kind, "payload": json.dumps(payload, default=str)},
            maxlen=settings.EVENT_STREAM_MAXLEN,
            approximate=True,
        )
    except Exception:
        logger.warning("event_buffer_unavailable", extra={"kind": kind}, exc_info=False)


def push_many(kind: str, payloads: list[dict[str, Any]]) -> None:
    for payload in payloads:
        push(kind, payload)
