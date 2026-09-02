# ops

The transactional outbox, the audit trail, and disruption handling: noticing that a flight is
no longer operating, and offering everyone booked on it a way out.

## Responsibilities

- Owns: `OutboxEvent`, `AuditLog`, `Disruption`, `RebookOption`, and the rebooking flow.
- Will own (later): `Notification`, `NotificationTemplate`, and the rest of the staff-facing
  `/ops/*` API.
- Does not own: the delivery of any particular side effect (the outbox stores the promise, the
  relay decides what to do with it), flight status itself (`apps.inventory`), or the reissue
  (`ticketing/services/exchange.py`).

## Key objects

| Object | Role |
|---|---|
| [services/outbox.py](services/outbox.py) `emit` | Write a side-effect promise inside the caller's transaction |
| [services/audit.py](services/audit.py) `record` | Append a before/after row for a state change |
| [models.py](models.py) `OutboxEvent` | `processed_at IS NULL` is the work queue |
| [models.py](models.py) `AuditLog` | Immutable history, indexed by `(object_type, object_id)` |
| [services/disruption.py](services/disruption.py) `classify` / `detect` | What is wrong with a flight, raised once |
| [services/disruption.py](services/disruption.py) `sweep` | The whole detect → notify pass |
| [services/rebook.py](services/rebook.py) `accept_rebooking` | Take an option, re-check seats, reissue |

## Invariants

- **`emit()` refuses to run outside a transaction.** An event written outside one can be delivered
  for work that later rolled back, which is the single failure the outbox exists to prevent — so
  the guard raises rather than trusting the caller.
- **Nothing that leaves the process happens inline.** No email, webhook, PDF or ClickHouse write
  inside a request transaction (CLAUDE.md invariant 5). Write the event; let the relay deliver it.
- **Delivery is at-least-once.** Every handler must be idempotent, keyed by `aggregate_id`.
- **The audit log is append-only.** Rows are never updated or deleted, including by the admin.
- **A disruption is raised once per flight and type.** The detector runs every five minutes; the
  unique partial index (`resolved_at IS NULL`) is the guard, not a prior read, so overlapping
  runs cannot notify the same passenger twelve times an hour.
- **A rebooking option holds no inventory.** It is a suggestion sitting in an inbox, so
  `accept_rebooking` re-reads availability under lock and returns 409 if the flight filled up.
- **The fare difference is waived.** The carrier caused the disruption, so `fare_delta` is zero
  and the booking's totals do not move — there is nothing to collect and nothing to refund.
- **Only a ticketed journey moves to `DISRUPTED`.** A booking still on hold can simply expire;
  `_mark_disrupted` checks the state machine rather than forcing it.

## Entry points

- `GET /api/v1/bookings/{pnr}/rebook-options` — owner, staff, or guest with `?last_name=`.
  Returns `[]` for an undisrupted booking rather than 404.
- `POST /api/v1/bookings/{pnr}/rebook` — take one option; `Idempotency-Key` required
- `GET /api/v1/ops/disruptions` — open disruptions, ops staff only
- Tasks: `ops.detect_disruptions` (beat, 5 min)
- `ops.relay_outbox` (beat, 5 s) is routed and scheduled in [config/celery.py](../../config/celery.py);
  the handler itself is not written yet, so events accumulate with `processed_at IS NULL`.

## Gotchas

- Event payloads are snapshots, not references. A handler that re-reads the aggregate sees the
  *current* state, which may have moved on since the event was written — put what the handler
  needs into the payload.
- `idx_outbox_pending` is partial (`processed_at IS NULL`). A query that filters on anything else
  will not use it.
- The relay is not implemented, so nothing drains the table yet. Anything counting on delivery —
  confirmation email, ClickHouse mirror — is still waiting on it. `flight_disrupted` is written
  the same way, so passengers are not actually emailed until the relay exists.
- A short delay is deliberately *not* a disruption. `DELAY_THRESHOLD_MINUTES` is 120; below that
  a passenger has nothing to act on and the notice is noise.
- Alternatives are searched same day first, then ±1 day (`REBOOK_DAY_OFFSETS`). A route with one
  daily operation therefore offers yesterday and tomorrow, which is correct, not a bug.
- Rebooking reuses `ticketing.exchange_tickets` with `from_status=REBOOKED`. The two paths differ
  only in who pays — keep them on the same code so coupon and conjunction handling cannot drift.

## Testing

    make test-be app=ops

Required: `emit()` outside a transaction raises; an event written in a rolled-back transaction
does not survive; a transition writes exactly one audit row with both sides of the change; a
short delay raises nothing; the same cancellation is flagged once; at most three options are
offered; a full alternative is not offered; an expired or filled option is refused; accepting one
withdraws the rest and costs the passenger nothing.
