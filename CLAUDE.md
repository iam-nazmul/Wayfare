# Wayfare — Agent & Developer Guide

Flight inventory, booking, and air-ticket management platform.
Full domain detail, schemas, and API catalogue: [SPEC.md](SPEC.md). This file is the working
contract — read it before writing code; read SPEC.md when you need the "why".

## Architecture

```
                              ┌──────────────────────────────────────────────┐
   Browser                    │  nginx (edge)                                │
   React 19 + Vite + TW4 ────▶│    /            → SPA (Vite dev / static)    │
   TanStack Query, Zustand    │    /api /admin  → Django (gunicorn+uvicorn)  │
                              └───────────────────┬──────────────────────────┘
                                                  │
                    ┌─────────────────────────────▼──────────────────────────────┐
                    │                    Django 5.2 + DRF                        │
                    │  views (validate) → services/ (domain) → models (invariants)│
                    │  selectors.py = every read, ownership-filtered              │
                    │                                                             │
                    │  accounts  catalog  inventory  pricing  booking             │
                    │  ticketing payments checkin     ops      analytics          │
                    └──┬──────────────┬───────────────┬──────────────┬───────────┘
                       │              │               │              │
          ┌────────────▼───┐   ┌──────▼──────┐  ┌─────▼──────┐  ┌───▼───────────────┐
          │  PostgreSQL 18 │   │   Redis 8   │  │  Celery 5  │  │ Redis Stream      │
          │  SYSTEM OF     │   │ cache(2)    │  │ critical   │  │ wayfare:events(6) │
          │  RECORD        │   │ locks(3)    │  │ default    │  └────────┬──────────┘
          │                │   │ rl(4)       │  │ notify     │           │
          │  bookings      │   │ offers(5)   │  │ analytics  │           │ XREADGROUP
          │  inventory     │   │ broker(0)   │  │ maintenance│           │ batch 5k / 5s
          │  tickets       │   │ results(1)  │  └─────┬──────┘           │
          │  payments      │   └─────────────┘        │                  │
          │  outbox ───────┼── relay_outbox (5s) ─────┘                  │
          └────────────────┘                                    ┌────────▼────────┐
                                                                │  ClickHouse 25.8│
   Provider (Stripe/sandbox) ──webhook──▶ /api/v1/webhooks/     │  events         │
   SPA ──card data, never our servers──▶ Provider SDK           │  search_log     │
                                                                │  api_request_log│
                                                                │  app_log        │
                                                                │  bookings_mirror│
                                                                │  + MV rollups   │
                                                                └─────────────────┘
```

**Data flow, one line each**
- *Search*: SPA → `POST /search/flights` → Redis cache hit, else Postgres candidates → connection
  build → price → signed offers (Redis, 15 min TTL).
- *Book*: offer → `SELECT … FOR UPDATE` on cabin+RBD → hold (20 min) → PNR.
- *Pay*: SPA ↔ provider → webhook → `handle_payment_succeeded` → holds become sales → `issue_tickets`.
- *Side effects*: never inline — write `OutboxEvent` in the same transaction, `relay_outbox` fans out.
- *Analytics*: `/collect` + middleware + log handler → Redis Stream → analytics worker → ClickHouse.

## Commands

```
make up                  # start the stack        make down / make clean
make migrate             # Django + ClickHouse (ch_migrate)
make seed                # demo data: bookable end-to-end in one command
make test                # pytest + vitest        make e2e (Playwright)
make lint                # ruff + mypy + eslint + tsc
make schema              # regenerate OpenAPI → frontend types (run after ANY serializer change)
make logs s=api          make shell / psql / chcli
```

## Invariants — breaking these is a bug, not a style choice

1. **Postgres is the only system of record.** ClickHouse is append-only, lossy, rebuildable. Never
   read it in a booking, payment, or ticketing path.
2. **Money never touches `float`.** `NUMERIC(12,2)` / `Decimal` / minor-unit integers on the wire.
   Every amount travels with its ISO-4217 currency. No bare numbers in serializers.
3. **Inventory changes inside a DB transaction** with `SELECT … FOR UPDATE` on `CabinConfig` and
   `BookingClass`, locked in `(flight_id, id)` order. Redis locks are an optimisation; the row lock
   is the guarantee. Never decrement inventory from Redis state.
4. **State transitions go through `booking/services/state.py::transition()`** — never assign
   `booking.status =` directly. Illegal transitions raise `InvalidTransition` → HTTP 409.
5. **Side effects go in the outbox.** No email, webhook, PDF, or ClickHouse write inside a request
   transaction.
6. **Mutating endpoints are idempotent.** `Idempotency-Key` required on bookings, payment intents,
   refunds, check-ins. Same key + same body → stored response; same key + different body → 422.
7. **Domain logic lives in `services/`.** Views validate and delegate. Serializers shape data. Models
   hold invariants. No business rules in `save()`, signals, or view bodies.
8. **Every non-staff read is ownership-filtered in `selectors.py`,** not in the view. Permissions
   fail closed: `IsAuthenticated` is the default, `AllowAny` is explicit.
9. **No card data, ever.** No PAN/CVV in the DB, logs, or fixtures. Brand + last4 + provider token only.
10. **No string-interpolated SQL** — ORM or parameterised queries, ClickHouse included.

## Conventions

**Backend**
- App layout: `models.py serializers.py views.py urls.py services/ selectors.py tasks.py admin.py tests/`
- Public identifiers in the API are `public_id` (UUIDv7); never expose integer PKs.
- Timestamps stored UTC; flight times also keep local naive time + IANA tz (schedules are authored local).
- Errors: RFC 9457 problem details via the shared exception handler. Never leak stack traces.
- Celery tasks are idempotent, keyed by a domain id, `acks_late`, retry with backoff + jitter.
  Money-touching tasks take a Redis lock *and* re-read state inside the transaction.
- Migrations are reviewed like code: no data loss, no unindexed FK, no lock-heavy DDL on hot tables.

**Frontend**
- `features/<domain>/` owns its components, hooks, and types. `components/` is design-system only.
- Server state = TanStack Query. Client state = Zustand (booking wizard, persisted to sessionStorage).
- The API client is **generated** from OpenAPI — never hand-write request types; run `make schema`.
- Analytics event names come from the typed union in `src/lib/events.ts`. Adding an event means
  extending that union; ad-hoc string names must not compile.
- Money is formatted through `lib/money.ts`. Dates through `lib/dates.ts`. No inline `toFixed(2)`.
- WCAG 2.2 AA: keyboard paths for seat map and calendar, `aria-live` on price/availability changes,
  no colour-only status.

**ClickHouse**
- DDL is versioned SQL in `backend/clickhouse/migrations/`, applied by `manage.py ch_migrate`.
- Ingestion is at-least-once — every table dedups by `event_id` (`ReplacingMergeTree`, `argMax`).
- Reports read materialised views, not raw `events`, whenever a rollup exists.

## Tooling in `.claude/`

**References** — the detailed conventions this file summarises. Read the relevant one before working
in that layer: [api-conventions](.claude/references/api-conventions.md) ·
[django-app-layout](.claude/references/django-app-layout.md) ·
[celery-task-patterns](.claude/references/celery-task-patterns.md) ·
[clickhouse-patterns](.claude/references/clickhouse-patterns.md) ·
[frontend-patterns](.claude/references/frontend-patterns.md) ·
[testing-patterns](.claude/references/testing-patterns.md) ·
[domain-glossary](.claude/references/domain-glossary.md)

**Skills** — `/new-django-app`, `/new-endpoint`, `/new-celery-task`, `/clickhouse-migration`,
`/module-readme`. Each carries the full checklist for that task; use them instead of improvising.

**Review agents** — `invariant-reviewer` (run before merging anything touching booking, inventory,
payments, or ticketing), `api-contract-guardian` (after serializer/view/URL changes),
`migration-safety` (whenever a migration is added), `airline-domain-expert` (domain rules).

## Documentation rules

- **CLAUDE.md** (this file): architecture diagram + actionable items only. Anything a developer or
  agent must *do* or *not do*. No prose history, no feature descriptions.
- **Module `README.md`** (one per Django app and per frontend feature): written for developers and
  agents — responsibilities, key models/services, entry points, invariants, gotchas, how to test it.
- **Root `README.md`**: written for *users of the application* — what Wayfare does, how to run it,
  how to use it. Not an internal design document.
- **Code comments: minimal.** Comment *why*, never *what*. If a line needs a comment to say what it
  does, rename it instead. Do not write a comment block per function by reflex.
- **Docstrings only where the contract is non-obvious.** When overriding, refer to the parent —
  `"""See ``BaseFareCalculator.quote``; adds child-discount handling."""` — rather than restating it.

## Before you finish

`make lint && make test`, plus `make schema` if any serializer, view, or URL changed (the frontend
types are generated from it). New endpoint → add happy-path, auth-denied, validation, and conflict
tests. Touching inventory, payments, or ticketing → the concurrency and idempotency cases in
SPEC.md §14 must still pass.

## Gotchas

- Search results are cached 60 s and tagged by route (`wf:idx:route:{O}:{D}`); an inventory or fare
  write must sweep those tags or the storefront serves stale prices.
- Offers are HMAC-signed and expire in 15 min — re-validate signature, expiry, *and* live
  availability at booking time. An unexpired offer is not a reservation.
- Webhooks arrive out of order and more than once. `ProviderWebhookEvent.provider_event_id` is
  unique; rely on it. Confirmation must also survive the webhook never arriving
  (`reconcile_pending_payments`, 5 min).
- Infants have no seat and must reference an adult on the same booking; pax type is derived from DOB
  at the *return* date.
- Cabin capacity is the hard ceiling even when RBD authorisations sum higher — that overbooking of
  *authorisations* is intentional, overselling *seats* is not.
