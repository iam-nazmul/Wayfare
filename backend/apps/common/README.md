# common

Cross-cutting primitives every other app builds on. No domain logic lives here.

## Responsibilities

- Owns: base model mixins, the `Money` value object, the RFC 9457 exception layer, cursor
  pagination, idempotency storage, Redis locking, request-id binding, JSON log formatting, health
  probes.
- Does not own: any business rule. If it knows what a booking is, it belongs elsewhere.

## Key objects

| Object | Role |
|---|---|
| [models.py](models.py) `TimestampedModel` | `created_at` / `updated_at` on everything |
| [models.py](models.py) `PublicIdModel` | UUIDv7 `public_id`; integer PKs never leave the process |
| [models.py](models.py) `IdempotencyKey` | Stored request hash + captured response, unique on `(scope, key)` |
| [money.py](money.py) `Money` | Frozen `(Decimal, currency)` pair with checked arithmetic |
| [fields.py](fields.py) `MoneyField` | Serializes a column pair as `{"amount", "currency"}` |
| [exceptions.py](exceptions.py) `DomainError` | Base for anything the API turns into a problem detail |
| [exceptions.py](exceptions.py) `problem_detail_handler` | The single DRF exception handler |
| [exceptions.py](exceptions.py) `TransientError` | The only exception Celery retries on |
| [idempotency.py](idempotency.py) `@idempotent` | Replay-safe POST decorator |
| [locks.py](locks.py) `redis_lock` | Advisory lock, *not* the correctness guarantee |
| [pagination.py](pagination.py) `WayfareCursorPagination` | Cursor paging with the `results/next/previous` envelope |
| [uuid7.py](uuid7.py) `uuid7` | Time-ordered ids so index inserts stay append-only |

## Invariants

- **`Money` never holds a float.** The constructor coerces through `Decimal(str(value))` and
  quantizes to 2dp. Passing a float in directly still works but rounds at construction — pass
  `Decimal` or `str`. Arithmetic across currencies raises `CurrencyMismatch` rather than silently
  adding USD to EUR.
- **`redis_lock` does not make an operation safe.** It reduces contention. Without a
  `select_for_update()` re-read inside the transaction, two workers that acquire the lock in
  sequence still act on stale rows, and inventory oversells.
- **`@idempotent` only stores 2xx responses.** A failed request leaves no key, so the client may
  retry the same key. Same key + different body hash raises `IdempotencyKeyReuse` (422).
- **`problem_detail_handler` remaps DRF's 400 to 422.** Field errors are flattened into
  `errors: [{field, message}]`. Adding a new `DomainError` subclass automatically gets the right
  shape — do not build error responses by hand anywhere else.
- **`JSONFormatter` redacts by substring match** on an allowlist (`password`, `token`, `doc_number`,
  `pan`, …). Logging a dict of user input under a key not on that list will leak it.

## Entry points

- HTTP: `GET /healthz` (liveness, no dependency checks), `GET /readyz` (Postgres + Redis +
  ClickHouse round-trips, 503 when degraded).
- Referenced from settings: `DEFAULT_PAGINATION_CLASS`, `EXCEPTION_HANDLER`, `LOGGING.formatters`,
  `MIDDLEWARE` (`RequestIDMiddleware`).

## Gotchas

- `readyz` reports a degraded ClickHouse but keeps Postgres and Redis status visible — it never
  raises, because a probe that throws tells you nothing about which dependency broke.
- `uuid7()` keeps a module-level counter for intra-millisecond ordering. It is process-local, which
  is fine: ordering only has to hold within one writer.
- `IdempotencyKey` rows are purged after 24h by `maintenance.purge_expired_idempotency_keys`. A
  client retrying with a key older than that gets a fresh execution, not a replay.

## Testing

    make test-be app=common

Cover `Money` arithmetic and rounding boundaries, the exception handler's status/code mapping, and
the idempotency replay + conflict paths.
