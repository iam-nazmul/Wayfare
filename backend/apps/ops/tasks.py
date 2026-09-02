import logging

from celery import shared_task

from .services.disruption import sweep

logger = logging.getLogger("wayfare.ops")


@shared_task(name="ops.detect_disruptions", queue="default", acks_late=True)
def detect_disruptions(limit: int = 500) -> dict[str, int]:
    """Compare flight state against what has already been raised, and offer a way out.

    Idempotent by construction: `Disruption` carries a unique partial index per flight and
    type, so a flight already flagged is skipped rather than re-notified every five minutes.
    """
    totals = sweep(limit=limit)
    if totals["disruptions"]:
        logger.warning("disruptions_swept", extra=totals)
    return totals
