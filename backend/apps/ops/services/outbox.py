from django.db import transaction
from django.utils import timezone

from ..models import OutboxEvent


def emit(
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    *,
    available_at=None,
) -> OutboxEvent:
    """Promise a side effect. Call inside the business transaction, never after it.

    Raises if there is no open transaction: an event written outside one can be delivered for
    work that later rolled back, which is the exact failure the outbox exists to prevent.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("emit() must be called inside a transaction — see CLAUDE.md rule 5.")

    return OutboxEvent.objects.create(
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        event_type=event_type,
        payload=payload,
        available_at=available_at or timezone.now(),
    )
