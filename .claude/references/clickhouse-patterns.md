# ClickHouse patterns

Authority: [SPEC.md](../../SPEC.md) §9. ClickHouse is **append-only, lossy, and rebuildable**. It
never participates in a booking, payment, or ticketing decision.

## Migrations

Versioned SQL in `backend/clickhouse/migrations/NNNN_description.sql`, applied by
`python manage.py ch_migrate`, tracked in `wayfare.schema_migrations`.

- Forward-only. Never edit an applied file — add a new one.
- Every statement `IF NOT EXISTS` / `IF EXISTS` so re-running is safe.
- Adding a column: `ALTER TABLE … ADD COLUMN … DEFAULT …`. Never drop a column that ingestion
  still writes — deploy the writer change first.

## Table conventions

- `MergeTree` for raw events; `ReplacingMergeTree(version_col)` where dedup matters;
  `AggregatingMergeTree` for rollup targets.
- `PARTITION BY toYYYYMM(...)` for long-lived tables, `toYYYYMMDD(...)` for logs.
- `ORDER BY` starts with the column you filter on most, ends with time.
- `LowCardinality(String)` for anything under ~10 k distinct values (codes, names, statuses).
- `TTL` on every table — no unbounded growth. 400 d events, 90 d request log, 30 d app log.
- `Decimal(12,2)` for money, matching Postgres. Never `Float`.

## Ingestion

Producers write to the Redis Stream `wayfare:events`; the analytics worker consumes with
`XREADGROUP` and batch-inserts.

```python
client.insert(
    "wayfare.events", rows,
    column_names=COLUMNS,
    column_type_names=COLUMN_TYPES,          # skips the server DESCRIBE round-trip
    settings={"async_insert": 1, "wait_for_async_insert": 0},
)
```

- Batch 5 000 rows or 5 s, whichever comes first. Never insert per event.
- Pass `column_type_names` on hot paths — it avoids a `DESCRIBE` per insert.
- Delivery is **at-least-once**: every table must be deduplicable by `event_id`.
- ClickHouse being down must never raise into a request. The worker retries with backoff; the
  stream is capped and trims oldest.
- `wayfare_event_stream_lag > 60s` is an alert.

## Querying

- Read materialised views, not raw `events`, whenever a rollup exists.
- Merge aggregate states with `-Merge`: `uniqMerge(sessions)`, `avgMerge(avg_cheapest)`.
- Always bound by the partition key: `WHERE event_time >= %(from)s AND event_time < %(to)s`.
  An unbounded scan of `events` is a review blocker.
- **Parameterised queries only** — `client.query(sql, parameters={...})`. String interpolation into
  ClickHouse SQL is treated the same as SQL injection in Postgres.
- Cap report spans at 400 days; cache report responses in Redis for 5 min.

## Dedup in reads

```sql
SELECT argMax(status, updated_at) AS status, booking_id
FROM wayfare.bookings_mirror
WHERE booked_at >= %(from)s
GROUP BY booking_id
```

Prefer `argMax` over `FINAL` on large scans — `FINAL` is fine for point lookups and small ranges.

## Rebuilding

`bookings_mirror` is fully reconstructible from Postgres via
`sync_bookings_to_clickhouse(full=True)`. Raw clickstream is not reconstructible — that is
accepted. Nothing financial may depend on it.
