---
name: new-celery-task
description: Add an idempotent Celery task with correct queue routing, locking, retry policy, beat schedule, and tests. Use when adding background work, a scheduled job, or an outbox event handler.
---

# New Celery task

Authority: [celery-task-patterns.md](../../references/celery-task-patterns.md).

## Decide first

**Is this a task at all?** If it is a side effect of a state change (email, webhook, analytics,
PDF), do **not** dispatch it from the request — write an `OutboxEvent` in the same transaction and
add a handler to the relay. Only work that is genuinely independent or scheduled becomes a
directly-dispatched task.

**Which queue?** `critical` for money/inventory, `default` for domain jobs, `notifications`,
`analytics`, `maintenance`. Route it explicitly in `config/celery.py::task_routes` — an unrouted
money task landing on `default` is a bug.

## Steps

1. **Write it in `tasks.py` as a thin wrapper** over a service function. Domain logic lives in
   `services/`, so it stays testable without Celery.

2. **Arguments are ids only.** JSON-serializable primitives. Never pass model instances.

3. **Make it idempotent.** Open by checking whether the effect already happened and returning early.
   Assume at-least-once delivery — retries, `acks_late` redelivery, duplicate webhooks.

4. **Lock and re-read** for anything touching money or inventory:
   ```python
   with redis_lock(f"wf:lock:booking:{booking_id}", timeout=60):
       with transaction.atomic():
           booking = Booking.objects.select_for_update().get(pk=booking_id)
   ```
   The Redis lock reduces contention; `select_for_update` is the guarantee.

5. **Retry policy.** `autoretry_for` transient errors only, `retry_backoff=True`,
   `retry_jitter=True`, `max_retries=5`. Validation and state errors must fail fast to
   `dead_letter`, not retry.

6. **Dispatch safely.** `transaction.on_commit(lambda: task.delay(obj.id))` — never `.delay()`
   inside an open transaction.

7. **Schedule it** (if periodic) in `config/celery.py` beat config, and add the row to
   [SPEC.md](../../../SPEC.md) §8.3 so the inventory stays accurate. Beat tasks must tolerate
   overlapping runs — claim work with `select_for_update(skip_locked=True)`.

8. **Tests:** direct call with `CELERY_TASK_ALWAYS_EAGER`, a double-invocation idempotency test,
   and `freezegun` for any time-window logic.

## Checklist

- [ ] Not better served by the outbox
- [ ] Queue routed explicitly
- [ ] Id arguments only
- [ ] Early-return idempotency guard
- [ ] Lock + `select_for_update` for money/inventory
- [ ] Transient-only retries, `on_commit` dispatch
- [ ] Beat entry added to SPEC.md §8.3
- [ ] Double-invocation test proves one effect
