# analytics

Clickstream and log ingestion into ClickHouse, plus the ops reports read back out of it.

## Responsibilities

- Owns: the `/collect` beacon endpoint, the Redis Stream buffer, the ClickHouse client and
  migrations, the flush worker, the Postgres→ClickHouse booking mirror, and the `/ops/reports/*`
  endpoints.
- Does not own: any booking, payment, or inventory decision. ClickHouse is append-only, lossy, and
  rebuildable — see CLAUDE.md invariant 1.

## Key objects

| Object | Role |
|---|---|
| [events.py](events.py) `push` | Buffer one event onto the Redis Stream. Never raises |
| [clickhouse.py](clickhouse.py) `insert_rows` | Batch insert with `async_insert=1` |
| [clickhouse.py](clickhouse.py) `query` | Parameterised reads only |
| [tasks.py](tasks.py) `flush_event_buffer` | `XREADGROUP` → batch insert → `XACK` |
| [middleware.py](middleware.py) `RequestLogMiddleware` | Feeds `wayfare.api_request_log` |
| [views.py](views.py) `CollectView` | `POST /api/v1/collect`, ≤100 events per batch |
| [management/commands/ch_migrate.py](management/commands/ch_migrate.py) | Applies `clickhouse/migrations/*.sql` |
| [reports.py](reports.py) `REPORTS` | The report catalogue, slug → query (SPEC.md §9.5) |
| [views.py](views.py) `OpsReportView` | `GET /ops/reports/{slug}` — window, cache, CSV, permissions |
| [tasks.py](tasks.py) `sync_bookings_to_clickhouse` | Incremental mirror, cursor on `updated_at` |
| [tasks.py](tasks.py) `rollup_daily_metrics` | Daily cheapest-fare snapshot for fare-trend |
| [devices.py](devices.py) `device_type` | Coarse UA bucket, so the funnel segments by device |

## Invariants

- **`push()` must never raise.** A dead Redis has to degrade analytics, not fail a booking. It
  catches broadly and logs a warning — that breadth is deliberate, not sloppiness.
- **Entries are acked only after a successful insert.** A ClickHouse failure returns early and
  leaves the entries pending, so the next tick retries them. This makes delivery at-least-once, so
  every table must dedup on `event_id`.
- **ClickHouse DDL is forward-only.** Never edit an applied file in `clickhouse/migrations/`; add a
  new numbered one. Applied names are tracked in `wayfare.schema_migrations`.
- **Column order in `tasks.py` must match the DDL.** `CLICKSTREAM_COLUMNS` and `REQUEST_LOG_COLUMNS`
  are positional. Adding a column to the table without adding it to the list inserts data into the
  wrong column silently.
- **Deploy the writer before the reader.** A migration that adds a column must ship before anything
  queries it, and a column the worker still writes must never be dropped.
- **Reports never touch a booking path.** They read ClickHouse, are cached five minutes, and are
  capped at a 400-day window, so a slow report cannot slow down a sale. `load-factor` is the one
  exception and reads Postgres — ops sizing capacity needs live inventory, not last night's mirror.
- **Report SQL is parameterised.** A date or route interpolated into ClickHouse SQL is treated as
  SQL injection (invariant 10); `clickhouse.query` takes a parameters dict and nothing else.
- **The mirror cursor advances only after a successful insert.** A ClickHouse failure re-sends the
  same window rather than skipping it; `bookings_mirror` is a ReplacingMergeTree keyed on
  `booking_id`, so a row seen twice collapses.

## Entry points

- HTTP: `POST /api/v1/collect` (AllowAny — the storefront is anonymous until checkout)
- HTTP: `GET /api/v1/ops/reports/{slug}` — ops staff only. Slugs: `funnel`, `search-conversion`,
  `revenue`, `load-factor`, `top-routes`, `abandonment`, `api-health`, `fare-trend`.
  `?date_from=&date_to=` (default 30 days, max 400); `Accept: text/csv` streams CSV.
- Tasks: `analytics.flush_event_buffer` (beat, 5s), `analytics.sync_bookings_to_clickhouse`
  (beat, 5min), `analytics.rollup_daily_metrics` (beat, daily)
- CLI: `python manage.py ch_migrate [--dry-run]`

## Gotchas

- The event name list in [serializers.py](serializers.py) must stay in step with
  `frontend/src/lib/events.ts`. They are the same taxonomy declared twice; a name the frontend sends
  that the serializer does not know is rejected as a validation error.
- `total_amount_usd` on the mirror is converted at sync time, not report time, so revenue across
  currencies is summable. A booking re-synced later is re-converted at the newer rate — acceptable
  for reporting, not for finance reconciliation, which reads the ledger in Postgres.
- The fare-trend report is only as good as `rollup_daily_metrics`, which snapshots from `Offer`
  rows. Those are deleted by `booking.expire_offers`, so a day the rollup misses is gone for good.
- `device_type` was added in `0003_device_type.sql`, which drops and recreates `funnel_daily_mv`.
  A materialised view only sees rows inserted *after* it exists, so the funnel's device split
  starts from that migration, not from the beginning of the events table.
- `ANALYTICS_ENABLED=0` disables buffering entirely. Test settings set it, so tests never reach for
  Redis or ClickHouse.
- The consumer group name is fixed (`wayfare-analytics`) and the consumer name is not unique per
  worker. Running more than one analytics worker means both claim as `worker-1`; give each a
  distinct `CONSUMER` before scaling out.

## Testing

    make test-be app=analytics

Required: `push()` stays silent when Redis is down; a failed insert leaves entries unacked; the
`/collect` endpoint rejects unknown event names and batches over 100; every catalogued report is
reachable and closed to non-ops callers; the window defaults to 30 days and refuses more than 400;
a second identical request is served from cache; CSV streams with the right headers; the mirror is
incremental and does not advance its cursor on failure.
