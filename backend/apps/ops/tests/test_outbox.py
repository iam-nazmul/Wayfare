import pytest
from django.db import transaction

from apps.ops.models import OutboxEvent
from apps.ops.services.outbox import emit

pytestmark = pytest.mark.django_db(transaction=True)


def test_emit_writes_a_pending_event():
    with transaction.atomic():
        event = emit("booking", "AB12CD", "booking_held", {"pnr": "AB12CD"})

    assert event.processed_at is None
    assert OutboxEvent.objects.filter(aggregate_id="AB12CD").count() == 1


def test_emit_outside_a_transaction_is_refused():
    """An event that outlives a rollback is the exact failure the outbox prevents."""
    with pytest.raises(RuntimeError):
        emit("booking", "AB12CD", "booking_held", {})


def test_a_rolled_back_event_does_not_survive():
    class Rollback(Exception):
        pass

    with pytest.raises(Rollback), transaction.atomic():
        emit("booking", "ZZ99ZZ", "booking_held", {})
        raise Rollback

    assert not OutboxEvent.objects.filter(aggregate_id="ZZ99ZZ").exists()
