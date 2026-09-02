# ops

The transactional outbox and the audit trail. Disruption, rebooking, notifications and the
`/ops/*` endpoints land here later; today this module exists so the rest of the system has a
safe place to promise a side effect and to record who changed what.

## Responsibilities

- Owns: `OutboxEvent`, `AuditLog`.
- Will own (later): `Disruption`, `RebookOption`, `Notification`, `NotificationTemplate`, and the
  staff-facing `/ops/*` API.
- Does not own: the delivery of any particular side effect. The outbox stores the promise; the
  relay and the individual handlers decide what to do with it.

## Key objects

| Object | Role |
|---|---|
| [services/outbox.py](services/outbox.py) `emit` | Write a side-effect promise inside the caller's transaction |
| [services/audit.py](services/audit.py) `record` | Append a before/after row for a state change |
| [models.py](models.py) `OutboxEvent` | `processed_at IS NULL` is the work queue |
| [models.py](models.py) `AuditLog` | Immutable history, indexed by `(object_type, object_id)` |

## Invariants

- **`emit()` refuses to run outside a transaction.** An event written outside one can be delivered
  for work that later rolled back, which is the single failure the outbox exists to prevent — so
  the guard raises rather than trusting the caller.
- **Nothing that leaves the process happens inline.** No email, webhook, PDF or ClickHouse write
  inside a request transaction (CLAUDE.md invariant 5). Write the event; let the relay deliver it.
- **Delivery is at-least-once.** Every handler must be idempotent, keyed by `aggregate_id`.
- **The audit log is append-only.** Rows are never updated or deleted, including by the admin.

## Entry points

- No HTTP surface yet.
- `ops.relay_outbox` (beat, 5 s) is routed and scheduled in [config/celery.py](../../config/celery.py);
  the handler itself is not written yet, so events accumulate with `processed_at IS NULL`.

## Gotchas

- Event payloads are snapshots, not references. A handler that re-reads the aggregate sees the
  *current* state, which may have moved on since the event was written — put what the handler
  needs into the payload.
- `idx_outbox_pending` is partial (`processed_at IS NULL`). A query that filters on anything else
  will not use it.
- The relay is not implemented, so nothing drains the table yet. Anything counting on delivery —
  confirmation email, ClickHouse mirror — is still waiting on it.

## Testing

    make test-be app=ops

Required: `emit()` outside a transaction raises; an event written in a rolled-back transaction
does not survive; a transition writes exactly one audit row with both sides of the change.
