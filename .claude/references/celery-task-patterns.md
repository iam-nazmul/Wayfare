# Celery task patterns

Authority: [SPEC.md](../../SPEC.md) §8.

## Queues

| Queue | Use |
|---|---|
| `critical` | Money and inventory: payments, ticketing, refunds, hold release |
| `default` | Schedules, availability recalculation, outbox relay, imports |
| `notifications` | Email/SMS render + send, PDF generation |
| `analytics` | Event flush, ClickHouse sync, rollups |
| `maintenance` | Cleanup, reconciliation, exports, FX |

Route explicitly in `config/celery.py::task_routes`. An unrouted task lands on `default` — for a
money-touching task that is a bug.

## Task template

```python
@shared_task(
    bind=True, queue="critical", acks_late=True,
    autoretry_for=(TransientError,), retry_backoff=True, retry_jitter=True,
    max_retries=5, soft_time_limit=270, time_limit=300,
)
def issue_tickets(self, booking_id: int) -> None:
    with redis_lock(f"wf:lock:booking:{booking_id}", timeout=60):
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking_id)
            if booking.status == BookingStatus.TICKETED:
                return                      # already done; at-least-once delivery
            ticketing.issue(booking)
```

Non-negotiable:

1. **Pass ids, never objects.** Arguments must be JSON-serializable; the row may have changed by
   the time the worker runs.
2. **Idempotent.** Every task starts by checking whether its effect already happened. Tasks run
   more than once — on retry, on redelivery after `acks_late`, on duplicate webhooks.
3. **Lock *and* re-read.** The Redis lock reduces contention; `select_for_update()` inside the
   transaction is the actual guarantee. Never rely on the lock alone.
4. **Transaction inside the task, not around the dispatch.** Publish work with
   `transaction.on_commit(lambda: task.delay(id))` — or better, via the outbox — so a task never
   observes a row that was rolled back.
5. **Retry only transient failures.** A `ValidationError` or `InvalidTransition` must not retry;
   let it fail and land in `dead_letter`.

## Outbox relay

Side effects are never dispatched from a request. Write the row in the same transaction:

```python
OutboxEvent.objects.create(
    aggregate_type="booking", aggregate_id=booking.id,
    event_type="booking_confirmed", payload={...},
)
```

`relay_outbox` (every 5 s, batch 200) claims rows with
`select_for_update(skip_locked=True)` on `processed_at IS NULL AND available_at <= now()`,
dispatches the matching handler, and stamps `processed_at`. Failures increment `attempts` and push
`available_at` out with exponential backoff; after 8 attempts the row is flagged for alerting.

Backlog > 1 000 rows for 5 minutes is an alert (`wayfare_outbox_backlog`).

## Beat schedule

Defined in `config/celery.py` and stored via `django-celery-beat`. Cadences live in
[SPEC.md](../../SPEC.md) §8.3 — keep the two in sync. Beat tasks must be safe to run concurrently
with themselves (a slow run overlapping the next tick), so they claim work with `skip_locked`
rather than assuming exclusivity.

## Testing

- Unit: call the task function directly, `CELERY_TASK_ALWAYS_EAGER=True` in `settings/test.py`.
- Idempotency: call the task twice, assert one ticket set, one charge, one inventory decrement.
- Expiry/backoff logic: `freezegun` rather than `sleep`.
- Never assert on a task by polling; assert on the state it produced.
