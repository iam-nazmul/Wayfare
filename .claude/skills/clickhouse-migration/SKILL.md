---
name: clickhouse-migration
description: Add or change a ClickHouse table, materialised view, or rollup, with the versioned SQL migration, ingestion wiring, and report query. Use when working on analytics, clickstream events, log tables, or ops reports.
---

# ClickHouse migration

Authority: [clickhouse-patterns.md](../../references/clickhouse-patterns.md) and
[SPEC.md](../../../SPEC.md) §9.

**Ground rule:** ClickHouse is append-only, lossy, and rebuildable. If a booking, payment, or
ticketing decision would read this data, it belongs in Postgres instead.

## Steps

1. **New file** `backend/clickhouse/migrations/NNNN_<description>.sql`. Forward-only — never edit an
   applied file. Every statement `IF NOT EXISTS` / `IF EXISTS` so re-running is safe.

2. **Table design.**
   - Engine: `MergeTree` (raw), `ReplacingMergeTree(version)` (dedup), `AggregatingMergeTree` (rollup target)
   - `PARTITION BY toYYYYMM(...)`, or `toYYYYMMDD(...)` for logs
   - `ORDER BY (<most-filtered column>, …, time)`
   - `LowCardinality(String)` under ~10 k distinct values
   - `Decimal(12,2)` for money — never `Float`
   - A `TTL` clause on every table

3. **Materialised view**, when a report would otherwise scan raw events: create the
   `AggregatingMergeTree` target table and the `MATERIALIZED VIEW … TO <target>` in the same
   migration. Store `-State` functions; read with `-Merge`.

4. **Ingestion.** If adding columns to `wayfare.events`, update `COLUMNS`/`COLUMN_TYPES` in the
   analytics worker **and deploy the writer before the reader depends on it**. Never drop a column
   the writer still sends. Keep the row deduplicable by `event_id`.

5. **Frontend events**, if this is clickstream: extend the typed union in
   `frontend/src/lib/events.ts` and the taxonomy in SPEC.md §9.4. Ad-hoc names must not compile.

6. **Report query**, if exposing one: bound by the partition key, parameterised
   (`client.query(sql, parameters={...})` — never f-strings), span capped at 400 days, Redis-cached
   5 min, CSV streaming on `Accept: text/csv`.

7. **Apply and test.**
   ```bash
   make migrate     # runs manage.py ch_migrate
   make test
   ```
   Test that DDL applies cleanly, that the MV output matches the same aggregation over raw rows, and
   that duplicate ingestion of one `event_id` yields one logical row.

## Checklist

- [ ] Nothing financial depends on this data
- [ ] Forward-only migration, idempotent statements
- [ ] `ORDER BY`, `PARTITION BY`, and `TTL` all set deliberately
- [ ] Dedup path exists (`event_id` + `ReplacingMergeTree`/`argMax`)
- [ ] Writer deployed before reader depends on new columns
- [ ] Queries parameterised and partition-bounded
- [ ] MV output verified against raw aggregation
