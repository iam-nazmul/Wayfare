# analytics

Clickstream and log ingestion into ClickHouse, plus the ops reports read back out of it.

## Responsibilities

- Owns: the `/collect` beacon endpoint, the Redis Stream buffer, the ClickHouse client and
  migrations, the flush worker, and (from M7) the report endpoints.
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

## Entry points

- HTTP: `POST /api/v1/collect` (AllowAny — the storefront is anonymous until checkout)
- Tasks: `analytics.flush_event_buffer` (beat, 5s), `analytics.sync_bookings_to_clickhouse`
  (beat, 5min), `analytics.rollup_daily_metrics` (beat, daily)
- CLI: `python manage.py ch_migrate [--dry-run]`

## Gotchas

- The event name list in [serializers.py](serializers.py) must stay in step with
  `frontend/src/lib/events.ts`. They are the same taxonomy declared twice; a name the frontend sends
  that the serializer does not know is rejected as a validation error.
- `sync_bookings_to_clickhouse` and `rollup_daily_metrics` are stubs returning 0 until M3 and M7
  respectively. They are wired into beat already so the schedule does not change later.
- `ANALYTICS_ENABLED=0` disables buffering entirely. Test settings set it, so tests never reach for
  Redis or ClickHouse.
- The consumer group name is fixed (`wayfare-analytics`) and the consumer name is not unique per
  worker. Running more than one analytics worker means both claim as `worker-1`; give each a
  distinct `CONSUMER` before scaling out.

## Testing

    make test-be app=analytics

Required: `push()` stays silent when Redis is down; a failed insert leaves entries unacked; the
`/collect` endpoint rejects unknown event names and batches over 100.
