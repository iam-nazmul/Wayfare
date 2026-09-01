# Wayfare — Flight & Air Ticket Management System

**Status:** Accepted v1.0 · **Date:** 2026-09-01 · **Owner:** nazmul@glascutr.com

Wayfare is a flight inventory, booking, and air-ticket management platform. It covers the full
commercial lifecycle of a seat: schedule → availability → fare → offer → order (PNR) → payment →
e-ticket → check-in → boarding pass → change/cancel/refund → revenue and clickstream analytics.

---

## 1. Scope

### 1.1 What Wayfare is

A **carrier-side / consolidator-side** system. The operator owns the inventory: schedules, cabins,
seat maps, fare products, and tax rules live in Wayfare's own database. There is no hard dependency
on an external GDS to be functional. External supply (GDS/NDC/other carriers) is modelled behind a
`SupplierAdapter` interface so it can be added later without reshaping the domain.

Three consumer surfaces, one API:

| Surface | Audience | Auth |
|---|---|---|
| Public storefront | Travellers | Anonymous → JWT on booking |
| Agency console | Travel agencies (B2B) | JWT + agency scope |
| Ops console | Airline staff: inventory, ticketing, disruption, refunds | JWT + staff role |

### 1.2 In scope (v1)

- Reference data: countries, cities, airports, airlines, aircraft types, currencies, FX rates.
- Schedule management: recurring schedules → materialised dated flights, with irregular-ops edits.
- Availability & seat inventory per cabin and per booking class (RBD), with oversell control.
- Fare products (fare families), fare rules, taxes/fees/surcharges, promo codes, currency display.
- One-way / round-trip / multi-city search with connection building (up to 2 stops).
- Offer → hold (TTL inventory lock) → order (PNR) → payment → e-ticket issuance.
- Passengers (ADT/CHD/INF), contact details, APIS/travel docs, SSRs.
- Ancillaries: paid seats, bags, meals, priority, insurance (as products + EMDs).
- Payments: card via provider abstraction (Stripe reference impl.), agency credit balance, 3DS,
  webhooks, refunds, void, partial refund.
- Ticketing: e-ticket with per-segment coupons, coupon state machine, void window, exchanges.
- Check-in, seat selection, boarding pass (PDF + PKPass-shaped payload), baggage tags stub.
- Disruption handling: schedule change, cancellation, rebooking offers, notification fan-out.
- Notifications: email (itinerary, e-ticket, reminders, disruption) + SMS hooks; PDF itineraries.
- Admin/ops console: inventory grid, PNR search & servicing, refunds queue, audit trail.
- Analytics: clickstream + application/API logs to ClickHouse; funnel, search, and revenue reports.

### 1.3 Out of scope (v1) — explicitly deferred

Interline/codeshare settlement (IATA BSP/ACH files), real GDS/NDC connectivity, loyalty/FFP accrual
and redemption, dynamic-pricing ML, cargo, crew/rostering, weight & balance, real DCS/ACARS
integration, multi-tenant white-label theming, native mobile apps.

### 1.4 Personas

| Persona | Needs |
|---|---|
| Traveller | Fast search, transparent pricing, self-service change/cancel, check-in |
| Agency agent | Multi-passenger bookings, credit-limit billing, servicing on behalf of client |
| Revenue analyst | Inventory & fare tuning, funnel and search-conversion reporting |
| Ops controller | Disruption handling, rebooking, refund approval, audit |
| Engineer/SRE | Reproducible local stack, observable services, safe deploys |

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **PNR** | Passenger Name Record — the order/reservation. 6-char alphanumeric locator. |
| **Segment** | One marketed flight leg inside an itinerary. |
| **Leg** | Physical departure→arrival hop of a flight (a segment may cover multiple legs). |
| **Cabin** | Physical class: `ECONOMY`, `PREMIUM_ECONOMY`, `BUSINESS`, `FIRST`. |
| **RBD / booking class** | Single-letter inventory bucket inside a cabin (Y, B, M, Q…). Price ladder. |
| **Fare family** | Marketed bundle: Basic / Standard / Flex — rules + included ancillaries. |
| **Fare basis** | Code identifying the priced fare (e.g. `QLOWBD`). |
| **Offer** | Priced, time-limited search result. Immutable, has an `offer_id` and expiry. |
| **Order** | Materialised booking created from an offer. |
| **Coupon** | Per-segment portion of an e-ticket; independently flown/refunded/exchanged. |
| **EMD** | Electronic Miscellaneous Document — receipt for an ancillary. |
| **SSR** | Special Service Request (WCHR, VGML, UMNR…). |
| **APIS** | Advance Passenger Information (travel document data). |
| **TTL hold** | Temporary inventory lock while payment completes. |
| **AVS/AVL** | Availability check against cabin + RBD inventory. |

---

## 3. Architecture

### 3.1 Component view

```
                    ┌──────────────────────────────────────────┐
  Browser ────────▶ │  nginx (edge)                            │
  (React SPA)       │   /            → SPA static / Vite dev   │
                    │   /api, /admin → Django (gunicorn)       │
                    └──────────────┬───────────────────────────┘
                                   │
              ┌────────────────────┴─────────────────────┐
              │              Django + DRF                │
              │  apps: accounts catalog inventory        │
              │        pricing booking ticketing         │
              │        payments checkin ops analytics    │
              └───┬──────────┬───────────┬───────────┬───┘
                  │          │           │           │
        ┌─────────▼──┐  ┌────▼─────┐ ┌───▼──────┐ ┌──▼────────────┐
        │ PostgreSQL │  │  Redis   │ │  Celery  │ │ Redis Stream  │
        │ system of  │  │ cache /  │ │ workers  │ │ wayfare:events│
        │  record    │  │ locks /  │ │ + beat   │ └──────┬────────┘
        └────────────┘  │ broker   │ └────┬─────┘        │
                        └──────────┘      │              │
                                          │       ┌──────▼─────────┐
                        outbox relay ─────┴──────▶│   ClickHouse   │
                                                  │ events, logs,  │
                                                  │ MVs, rollups   │
                                                  └────────────────┘
```

### 3.2 Design rules

1. **Postgres is the only system of record.** ClickHouse is append-only and disposable; losing it
   loses reporting, never money or bookings.
2. **Money is never floating point.** `NUMERIC(12,2)` in Postgres, `Decimal` in Python, minor units
   (integer cents) on the wire. Every amount carries an ISO-4217 currency.
3. **Every state-changing endpoint is idempotent** via an `Idempotency-Key` header stored in
   `payments_idempotency_key` / `booking_idempotency_key` with the hashed request body and the
   captured response.
4. **Inventory decrements happen inside a Postgres transaction** with `SELECT … FOR UPDATE`, never
   from Redis alone; Redis holds only advisory locks and short-TTL cached availability.
5. **Side effects go through a transactional outbox** (`ops_outbox_event`), relayed by Celery.
   No email, webhook, or ClickHouse write happens inside a request transaction.
6. **Domain logic lives in `services/`**, not in serializers, views, or model `save()`. Views
   validate and delegate; models hold invariants and constraints.
7. **Search is read-only and cached.** Booking is write-heavy and locked. They never share code paths.

### 3.3 Technology and pinned versions

Pins are the target at project start; the scaffold step verifies latest patch releases.

| Layer | Choice | Version |
|---|---|---|
| Language | Python | 3.13 |
| Web framework | Django | 5.2 LTS (6.x-compatible code) |
| API | Django REST Framework | 3.16 |
| Schema/docs | drf-spectacular (OpenAPI 3.1) | 0.28 |
| Auth | djangorestframework-simplejwt | 5.5 |
| Filtering | django-filter | 25.x |
| Async tasks | Celery + django-celery-beat | 5.5 / 2.8 |
| Cache/broker/locks | Redis | 8.x |
| Main DB | PostgreSQL | 18 |
| Analytics DB | ClickHouse | 25.8 LTS |
| CH driver | clickhouse-connect | 0.9.x |
| App server | gunicorn + uvicorn worker | 23.x |
| Frontend | React + TypeScript | 19 / 5.7 |
| Bundler | Vite | 7 |
| Styling | Tailwind CSS (`@tailwindcss/vite`) | 4.x |
| Server state | TanStack Query | 5.x |
| Client state | Zustand | 5.x |
| Routing | React Router | 7.x |
| Forms | react-hook-form + zod | 7.x / 3.x |
| API client | openapi-typescript + generated fetch client | — |
| Node | Node.js | 22 LTS |
| Orchestration | Docker Compose | v2 |

---

## 4. Repository layout

```
wayfare/
├── docker-compose.yml              # dev stack
├── docker-compose.prod.yml         # overrides: gunicorn, nginx-served SPA, no bind mounts
├── .env.example
├── Makefile
├── README.md
├── SPEC.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml              # uv-managed deps, ruff + mypy config
│   ├── manage.py
│   ├── config/
│   │   ├── settings/{base,dev,prod,test}.py
│   │   ├── urls.py  asgi.py  wsgi.py  celery.py
│   ├── apps/
│   │   ├── common/        # base models, mixins, pagination, errors, idempotency, money
│   │   ├── accounts/      # users, travellers, agencies, roles
│   │   ├── catalog/       # airports, airlines, aircraft, currencies, FX
│   │   ├── inventory/     # schedules, flights, cabins, RBDs, seat maps, availability
│   │   ├── pricing/       # fare products, rules, taxes, promos, quote engine
│   │   ├── booking/       # search, offers, holds, PNRs, passengers, ancillaries
│   │   ├── ticketing/     # e-tickets, coupons, EMDs, exchanges
│   │   ├── payments/      # intents, providers, refunds, ledger, webhooks
│   │   ├── checkin/       # check-in, seat assignment, boarding passes
│   │   ├── ops/           # disruptions, rebooking, notifications, audit, outbox
│   │   └── analytics/     # collector endpoint, CH client, schema migrations, reports
│   ├── clickhouse/
│   │   └── migrations/0001_init.sql …
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── vite.config.ts  tailwind is imported in src/index.css
│   ├── package.json  tsconfig.json
│   └── src/
│       ├── main.tsx  App.tsx  router.tsx
│       ├── api/          # generated client + hooks
│       ├── components/   # design-system primitives
│       ├── features/     # search, booking, checkin, manage, agency, ops
│       ├── lib/          # analytics.ts, money.ts, dates.ts, auth.ts
│       └── styles/
└── ops/
    ├── nginx/default.conf
    └── clickhouse/config.d/*.xml
```

Each Django app follows: `models.py`, `serializers.py`, `views.py`, `urls.py`, `services/`,
`selectors.py`, `tasks.py`, `admin.py`, `migrations/`, `tests/`.

---

## 5. Data model (PostgreSQL)

Conventions: `BigAutoField` PKs internally, **UUIDv7 public identifiers** (`public_id`) exposed in
the API, `created_at`/`updated_at` on every table, soft delete only where servicing requires history.
All timestamps stored UTC; flight times additionally stored as **local naive time + IANA tz** because
schedules are authored in local time.

### 5.1 accounts

```
User(id, email UNIQUE, password, first_name, last_name, phone, locale, is_staff,
     is_active, mfa_enabled, last_login_at)
Role(id, code, name)                       # TRAVELLER, AGENCY_AGENT, AGENCY_ADMIN,
UserRole(user, role, agency NULL)          # OPS_AGENT, TICKETING, FINANCE, SUPERADMIN
Traveller(id, user FK, first_name, last_name, dob, gender, nationality,
          doc_type, doc_number, doc_expiry, doc_issuing_country, is_primary)
Agency(id, name, iata_code, currency, credit_limit, balance, status, billing_address)
AgencyMember(agency, user, role, commission_pct)
```

Credit-limit rule: an agency booking may be confirmed without card capture while
`balance + booking_total <= credit_limit`; otherwise it falls back to card payment.

### 5.2 catalog

```
Country(iso2 PK, iso3, name, phone_prefix)
City(id, name, country, timezone, iata_code NULL)
Airport(id, iata_code UNIQUE, icao_code, name, city, country, timezone,
        latitude, longitude, is_active)
Airline(id, iata_code UNIQUE, icao_code, name, country, logo_url, is_active,
        ticketing_prefix)                  # 3-digit e-ticket prefix, e.g. 176
Aircraft(id, iata_type_code, name, manufacturer, total_seats_default)
Currency(code PK, name, symbol, minor_units)
ExchangeRate(base, quote, rate, valid_from, source)   # UNIQUE(base, quote, valid_from)
```

### 5.3 inventory

```
Route(id, airline, origin_airport, destination_airport, is_active)

FlightSchedule(id, airline, flight_number, route, aircraft,
               dep_time_local, arr_time_local, arrival_day_offset,
               days_of_week BIT(7), effective_from, effective_to,
               seat_map_template, status)
  # a repeating pattern; materialised into Flight rows by a Celery job

Flight(id, public_id, schedule FK NULL, airline, flight_number,
       origin_airport, destination_airport, aircraft, seat_map_template,
       departure_utc, arrival_utc, departure_local, arrival_local,
       duration_minutes, status, gate, terminal, actual_departure_utc,
       delay_minutes, version)
  UNIQUE(airline, flight_number, departure_utc)
  INDEX (origin_airport, destination_airport, departure_utc)
  INDEX (departure_utc) WHERE status IN ('SCHEDULED','DELAYED')

CabinConfig(id, flight, cabin, capacity, seats_sold, seats_held,
            oversell_allowance)
  # authoritative physical capacity per cabin
  CHECK (seats_sold + seats_held <= capacity + oversell_allowance)

BookingClass(id, flight, cabin_config, rbd CHAR(1), authorised, sold, held,
             is_open, sort_order)
  # nested inventory: sum(authorised) may exceed cabin capacity; cabin wins
  UNIQUE(flight, rbd)

SeatMapTemplate(id, name, aircraft, layout JSONB)   # rows, columns, exits, cabins
Seat(id, flight, cabin, row, column, seat_number, characteristics ARRAY,
     is_exit_row, is_blocked, seat_fee_amount, seat_fee_currency, status)
  UNIQUE(flight, seat_number)
  # status: AVAILABLE | HELD | ASSIGNED | BLOCKED
```

`Flight.status`: `SCHEDULED | DELAYED | BOARDING | DEPARTED | ARRIVED | CANCELLED | DIVERTED`.

### 5.4 pricing

```
FareFamily(id, airline, code, name, cabin, tier, includes JSONB,
           changeable, change_fee, refundable, refund_fee, baggage_allowance JSONB)
Fare(id, airline, origin_airport, destination_airport, cabin, rbd,
     fare_family, fare_basis, base_amount, currency, passenger_type,
     min_stay_days, max_stay_days, advance_purchase_days,
     valid_from, valid_to, is_active)
  INDEX (origin_airport, destination_airport, cabin, valid_from, valid_to)
TaxRule(id, code, name, country NULL, airport NULL, applies_to,
        calc_type, value, currency, is_active)   # calc_type: FIXED | PERCENT
FeeRule(id, code, name, scope, calc_type, value, currency)  # OB fees, service fees
PromoCode(id, code UNIQUE, discount_type, value, currency, max_uses,
          uses, per_user_limit, valid_from, valid_to, conditions JSONB, is_active)
PromoRedemption(promo, user, booking, redeemed_at)
```

### 5.5 booking

```
SearchQuery(id, public_id, user NULL, session_id, origin, destination,
            depart_date, return_date, trip_type, pax_adults, pax_children,
            pax_infants, cabin, currency, created_at)
            # thin row; the fat analytics record goes to ClickHouse

Offer(id, offer_id UUID UNIQUE, search_query, itinerary JSONB, price_breakdown JSONB,
      total_amount, currency, fare_family, seats_remaining, expires_at, signature)
      # cached in Redis for TTL, persisted for audit; `signature` = HMAC over the
      # priced payload so a client cannot tamper with an offer before booking

Booking(id, public_id, pnr CHAR(6) UNIQUE, user NULL, agency NULL,
        status, trip_type, currency, base_amount, tax_amount, fee_amount,
        ancillary_amount, discount_amount, total_amount, paid_amount,
        balance_due, contact_email, contact_phone, promo_code NULL,
        hold_expires_at, booked_at, cancelled_at, cancellation_reason,
        source_channel, version)
  INDEX (contact_email), INDEX (status, hold_expires_at)

BookingSegment(id, booking, flight, sequence, cabin, rbd, fare_basis,
               fare_family, marketing_flight_number, status, baggage_allowance)
Passenger(id, booking, type, first_name, last_name, dob, gender, nationality,
          doc_type, doc_number, doc_expiry, frequent_flyer_number,
          associated_adult FK NULL)      # infants ride with an adult
SeatAssignment(id, booking, passenger, segment, seat, amount, currency, status)
SpecialServiceRequest(id, booking, passenger, segment NULL, code, text, status)

AncillaryProduct(id, code, name, category, pricing_type, base_amount, currency,
                 is_per_segment, is_active)         # BAG, MEAL, PRIORITY, INSURANCE
BookingAncillary(id, booking, passenger, segment NULL, product, quantity,
                 unit_amount, total_amount, currency, status, emd FK NULL)

InventoryHold(id, booking NULL, offer_id, flight, cabin, rbd, seats,
              expires_at, released_at, hold_key)
  INDEX (expires_at) WHERE released_at IS NULL
```

**PNR generation:** 6 chars from `ABCDEFGHJKLMNPQRSTUVWXYZ0123456789` (no I/O to avoid confusion),
generated with `secrets.choice`, retried on unique-violation up to 5 times.

**Booking status machine**

```
DRAFT ──create offer──▶ HELD ──payment authorised──▶ PENDING_TICKETING
  │                      │                                │
  │                      ├── hold TTL expires ──▶ EXPIRED │
  │                      └── user cancels ──────▶ CANCELLED
  └── abandoned ──▶ EXPIRED                               │
                                                          ▼
CONFIRMED ◀── payment captured ──────────────────── TICKETED
  │                                                       │
  ├── change requested ──▶ CHANGE_PENDING ──▶ TICKETED (new coupons)
  ├── carrier cancels ───▶ DISRUPTED ──▶ REBOOKED | REFUNDED
  └── cancel ────────────▶ CANCELLED ──▶ REFUND_PENDING ──▶ REFUNDED
```

Legal transitions are declared in `booking/services/state.py` as a frozen dict and enforced by
`transition(booking, to_status, actor, reason)`, which writes an `ops_audit_log` row. Any illegal
transition raises `InvalidTransition` (HTTP 409).

### 5.6 ticketing

```
Ticket(id, ticket_number CHAR(13) UNIQUE, booking, passenger, issuing_airline,
       issued_at, issued_by, status, fare_amount, tax_amount, total_amount,
       currency, fare_calculation, conjunction_of FK NULL)
TicketCoupon(id, ticket, segment, coupon_number, status, flown_at,
             exchanged_to FK NULL, refunded_at)
EMD(id, emd_number CHAR(13) UNIQUE, booking, passenger, ancillary,
    amount, currency, status, issued_at)
TicketEvent(id, ticket, event_type, actor, payload JSONB, created_at)
```

**Ticket number:** `AAA` (3-digit airline prefix) + `NNNNNNNNN` (9-digit serial from a Postgres
sequence per airline) + check digit = `serial mod 7`. Validated on write.

**Coupon status:** `OPEN → CHECKED_IN → LIFTED/FLOWN`, plus `EXCHANGED`, `REFUNDED`, `VOID`.
Void is only allowed on the day of issue before any coupon leaves `OPEN` (the "void window").

### 5.7 payments

```
PaymentIntent(id, public_id, booking, provider, provider_intent_id,
              amount, currency, status, client_secret, capture_method,
              three_ds_status, idempotency_key, expires_at)
Payment(id, public_id, booking, intent, method, provider, provider_charge_id,
        amount, currency, status, card_brand, card_last4, authorised_at,
        captured_at, failure_code, failure_message)
Refund(id, public_id, booking, payment, amount, currency, status, reason,
       requested_by, approved_by, provider_refund_id, processed_at,
       penalty_amount, refundable_amount)
LedgerEntry(id, booking, entry_type, debit, credit, currency, balance_after,
            reference, created_at)      # append-only, never updated
ProviderWebhookEvent(id, provider, provider_event_id UNIQUE, event_type,
                     payload JSONB, signature_verified, processed_at, attempts)
IdempotencyKey(id, scope, key, request_hash, response_status,
               response_body JSONB, created_at)   UNIQUE(scope, key)
```

Payment provider is abstracted:

```python
class PaymentProvider(Protocol):
    def create_intent(self, *, amount: Money, booking_ref: str,
                      idempotency_key: str, metadata: dict) -> IntentResult: ...
    def capture(self, intent_id: str, amount: Money | None = None) -> ChargeResult: ...
    def void(self, intent_id: str) -> ChargeResult: ...
    def refund(self, charge_id: str, amount: Money,
               idempotency_key: str) -> RefundResult: ...
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent: ...
```

Implementations: `StripeProvider` (reference), `AgencyCreditProvider`, `SandboxProvider` (dev/tests,
deterministic outcomes keyed off card number: `4242…` succeeds, `4000…0002` declines, `4000…3220`
requires 3DS). **No PAN, CVV, or full card data ever reaches Wayfare** — the SPA collects card data
directly with the provider's SDK, keeping the deployment in PCI SAQ-A scope.

### 5.8 checkin & ops

```
CheckIn(id, booking, passenger, segment, status, checked_in_at, channel,
        seat, bags_count, boarding_group, sequence_number)
BoardingPass(id, checkin, barcode_data, format, issued_at, pdf_url,
             gate, boarding_time, zone)
Disruption(id, flight, type, reason, detected_at, resolved_at, notes)
RebookOption(id, disruption, booking, proposed_flight, fare_delta,
             status, expires_at)
NotificationTemplate(id, code UNIQUE, channel, subject, body_html, body_text, locale)
Notification(id, booking NULL, user NULL, channel, template, to_address,
             payload JSONB, status, provider_message_id, sent_at, error)
AuditLog(id, actor NULL, actor_type, action, object_type, object_id,
         before JSONB, after JSONB, ip, user_agent, request_id, created_at)
OutboxEvent(id, aggregate_type, aggregate_id, event_type, payload JSONB,
            available_at, processed_at, attempts, last_error)
  INDEX (processed_at, available_at) WHERE processed_at IS NULL
```

Boarding pass barcode is IATA BCBP M-format (PDF417 payload string), rendered into the PDF and
returned as raw data for wallet integrations.

---

## 6. Core workflows

### 6.1 Search → offer

```
Client                API                Redis            Postgres
  │  GET /search       │                  │                  │
  ├───────────────────▶│  cache key =     │                  │
  │                    │  hash(O,D,dates, │                  │
  │                    │  pax,cabin,cur)  │                  │
  │                    ├─────get─────────▶│                  │
  │                    │◀──hit (60 s)─────┤                  │
  │◀───200 offers──────┤                  │                  │
  │                    │  on miss:        │                  │
  │                    ├──flight candidates by O/D/date──────▶│
  │                    ├──connection build (≤2 stops, MCT)───│
  │                    ├──availability per cabin/RBD─────────▶│
  │                    ├──price each itinerary (fare+tax+fee)│
  │                    ├──sign + store offers, TTL 15 min────▶│ (+Redis)
  │                    ├──emit search_performed ──▶ event stream
  │◀───200 offers──────┤
```

Rules:
- **Connection building:** BFS over flights departing within `[arrival + MCT, arrival + 12h]`.
  MCT (minimum connect time) defaults 45 min domestic / 90 min international, overridable per airport.
- Discard itineraries where total duration > 3× the shortest non-stop, or that backtrack (a leg
  moving away from the destination by more than 25% of great-circle distance).
- Price: lowest open RBD per cabin whose `authorised - sold - held >= requested_seats`
  **and** whose cabin has capacity. Fare selection honours advance-purchase and min/max stay.
- Offers are **signed** (`HMAC-SHA256(offer payload, SECRET_KEY)`) and expire in 15 minutes.
  Booking re-validates the signature, expiry, and live availability before holding.
- Search never writes to Postgres on the hot path except the thin `SearchQuery` row (batched).
- Timeout budget: 800 ms p95. Hard cap 3 s, after which partial results are returned with
  `"partial": true`.

### 6.2 Offer → hold → PNR

1. `POST /bookings` with `offer_id`, passengers, contact, optional ancillaries, `Idempotency-Key`.
2. Serializer validates: pax counts match the offer, infants ≤ adults, DOB consistent with pax type
   (ADT ≥ 12 y, CHD 2–11, INF < 2 at *return* date), documents present for international.
3. In one transaction:
   - `SELECT … FOR UPDATE` on `CabinConfig` and `BookingClass` rows for every segment
     (ordered by `flight_id, id` to prevent deadlock),
   - re-check availability, increment `held`, insert `InventoryHold` rows,
   - create `Booking` (status `HELD`, `hold_expires_at = now + 20 min`), segments, passengers,
   - reserve requested seats (`Seat.status = HELD`),
   - insert `OutboxEvent(booking_held)`.
4. Response `201` with PNR, price breakdown, `hold_expires_at`.
5. `release_expired_holds` (Celery beat, every 60 s) reverses any hold past its TTL and moves the
   booking to `EXPIRED`.

### 6.3 Payment → ticketing

1. `POST /bookings/{pnr}/payment-intents` → provider intent, status `HELD` unchanged.
2. Client confirms with the provider SDK (3DS handled client-side).
3. Provider webhook `payment_intent.succeeded` → signature verified → `ProviderWebhookEvent`
   inserted (unique on `provider_event_id`, so replays are no-ops) → `handle_payment_succeeded` task.
4. That task, transactionally: records `Payment`, ledger entries, converts holds into sales
   (`held -= n; sold += n`), seats `HELD → ASSIGNED`, booking → `PENDING_TICKETING`,
   outbox `booking_confirmed`.
5. `issue_tickets` task: allocates ticket numbers, creates `Ticket` + one `TicketCoupon` per segment,
   issues EMDs for ancillaries, booking → `TICKETED`, outbox `ticket_issued`.
6. Notification worker renders and sends the itinerary + e-ticket PDF.

The client also polls `GET /bookings/{pnr}` (or holds an SSE stream on
`/bookings/{pnr}/events`) so confirmation does not depend on the webhook round-trip being visible
to the browser. If no webhook arrives within 3 minutes, `reconcile_payment` pulls the intent status
from the provider directly.

### 6.4 Change, cancel, refund

- **Cancel** → evaluate `FareFamily.refundable` + time-to-departure ladder → compute
  `refundable_amount = paid - penalty - non-refundable taxes` → create `Refund(status=PENDING)`.
  Auto-approve under `REFUND_AUTO_APPROVE_LIMIT` (default 500 USD equivalent); otherwise it lands in
  the ops refund queue. On approval: provider refund → coupons `REFUNDED` → inventory released →
  booking `REFUNDED`.
- **Change** → search for the new segment, price the difference (`new fare - old fare + change fee`,
  never negative unless the fare family allows residual value) → hold the new inventory → collect the
  delta → exchange: old coupons `EXCHANGED`, new ticket issued with `conjunction_of` linkage.
- **Void** → same-day, coupons untouched → provider void, booking `CANCELLED`, no penalty.

### 6.5 Disruption

`detect_disruptions` (beat, every 5 min) compares `Flight.status`/`delay_minutes` against last-known
state. On cancellation or a delay > 120 min: create `Disruption`, find affected bookings, generate
up to 3 `RebookOption`s (same day, then ±1 day, same cabin, fare delta waived), notify passengers,
expose the options under `GET /bookings/{pnr}/rebook-options`.

### 6.6 Check-in

Opens `T-48h`, closes `T-60min` (configurable per airline). Requires complete APIS for international
flights. Assigns a seat if none held, generates a `BoardingPass` with BCBP barcode and PDF, and
emits `checkin_completed`.

---

## 7. REST API

Base: `/api/v1`. JSON only. `drf-spectacular` serves the schema at `/api/schema/`, Swagger UI at
`/api/docs/`. The frontend client is generated from that schema — **the schema is the contract**.

### 7.1 Conventions

- **Auth:** `Authorization: Bearer <access>` (SimpleJWT, access 15 min, refresh 7 d, rotated with
  blacklist). Refresh token is stored in an `HttpOnly; Secure; SameSite=Lax` cookie.
- **Pagination:** cursor-based, `?cursor=&page_size=` (max 100). Envelope:
  `{"results": [...], "next": "...", "previous": null}`.
- **Filtering/ordering:** django-filter; `?ordering=-departure_utc`.
- **Errors:** RFC 9457 problem details.
  ```json
  { "type": "https://wayfare.dev/errors/inventory-unavailable",
    "title": "Requested seats are no longer available",
    "status": 409, "detail": "Only 1 seat remains in class Q on WF120",
    "code": "inventory_unavailable", "request_id": "01J…",
    "errors": [{"field": "passengers", "message": "…"}] }
  ```
- **Idempotency:** required on `POST /bookings`, `/payment-intents`, `/refunds`, `/checkins`.
  Replay with the same key + same body returns the stored response; different body → `422`.
- **Concurrency:** `If-Match` / `ETag` on booking mutations; mismatch → `412`.
- **Money on the wire:** `{"amount": "412.50", "currency": "USD"}` (decimal string, never float).
- **Versioning:** URL major version; additive changes only inside a version.

### 7.2 Endpoint catalogue

**Auth & accounts**

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create traveller account |
| POST | `/auth/login` | Obtain token pair |
| POST | `/auth/refresh` | Rotate access token |
| POST | `/auth/logout` | Blacklist refresh token |
| POST | `/auth/password/reset` · `/reset/confirm` | Password reset |
| GET/PATCH | `/me` | Profile |
| GET/POST/PATCH/DELETE | `/me/travellers[/{id}]` | Saved passengers |
| GET | `/me/bookings` | Booking history |

**Catalog (public, cached 24 h)**

| Method | Path | Purpose |
|---|---|---|
| GET | `/airports?q=&country=` | Typeahead (trigram search on code/name/city) |
| GET | `/airlines` · `/aircraft` · `/currencies` | Reference data |

**Search & offers**

| Method | Path | Purpose |
|---|---|---|
| POST | `/search/flights` | Search; body carries slices + pax + cabin + currency |
| GET | `/search/flights/{search_id}/offers?sort=&stops=&airline=` | Paginated, filterable results |
| GET | `/offers/{offer_id}` | Re-price and re-validate an offer |
| GET | `/search/calendar?origin=&destination=&month=` | Cheapest-per-day grid (materialised nightly) |

Request body:

```json
{ "trip_type": "ROUND_TRIP",
  "slices": [{"origin":"DAC","destination":"DXB","date":"2026-10-12"},
             {"origin":"DXB","destination":"DAC","date":"2026-10-20"}],
  "passengers": {"adults": 2, "children": 1, "infants": 0},
  "cabin": "ECONOMY", "currency": "USD", "max_stops": 1 }
```

**Bookings**

| Method | Path | Purpose |
|---|---|---|
| POST | `/bookings` | Create PNR from an offer (holds inventory) |
| GET | `/bookings/{pnr}` | Retrieve (auth, or `pnr` + `last_name` for guests) |
| PATCH | `/bookings/{pnr}/contact` | Update contact details |
| POST | `/bookings/{pnr}/passengers/{id}/documents` | APIS |
| POST | `/bookings/{pnr}/ancillaries` · DELETE `/{id}` | Bags, meals, priority |
| GET | `/bookings/{pnr}/seatmap?segment=` | Seat map with prices and availability |
| POST | `/bookings/{pnr}/seats` | Assign/change seats |
| POST | `/bookings/{pnr}/cancel` | Cancel + quote refund |
| POST | `/bookings/{pnr}/change/quote` · `/change/confirm` | Exchange flow |
| GET | `/bookings/{pnr}/rebook-options` · POST `/rebook` | Disruption self-service |
| GET | `/bookings/{pnr}/documents/itinerary.pdf` | Signed, expiring URL |
| GET | `/bookings/{pnr}/events` | SSE status stream |

**Payments**

| Method | Path | Purpose |
|---|---|---|
| POST | `/bookings/{pnr}/payment-intents` | Create intent |
| GET | `/payment-intents/{id}` | Poll status |
| POST | `/webhooks/payments/{provider}` | Provider callback (signature-verified, unauthenticated) |
| GET | `/bookings/{pnr}/payments` · `/refunds` | History |

**Ticketing**

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{pnr}/tickets` | E-tickets + coupon status |
| GET | `/tickets/{number}` | Ticket detail (staff/owner) |
| POST | `/tickets/{number}/void` | Void within window (staff) |

**Check-in**

| Method | Path | Purpose |
|---|---|---|
| GET | `/checkin/eligibility?pnr=&last_name=` | Window + blocking reasons |
| POST | `/checkin` | Check in one or more passengers/segments |
| GET | `/checkin/{id}/boarding-pass.pdf` · `.json` | BCBP payload / PDF |

**Ops (staff scopes)**

| Method | Path | Purpose |
|---|---|---|
| GET/POST/PATCH | `/ops/schedules[/{id}]` | Schedule CRUD |
| POST | `/ops/schedules/{id}/materialise` | Generate dated flights for a window |
| GET/PATCH | `/ops/flights[/{id}]` | Flight ops: status, gate, delay, cancel |
| GET/PATCH | `/ops/flights/{id}/inventory` | Cabin + RBD authorisations |
| GET/POST/PATCH | `/ops/fares[/{id}]` · `/ops/fare-families` | Pricing |
| GET | `/ops/bookings?status=&flight=&pax=` | PNR search |
| POST | `/ops/bookings/{pnr}/force-cancel` · `/reissue` | Servicing |
| GET/POST | `/ops/refunds` · `/refunds/{id}/approve` · `/reject` | Refund queue |
| GET | `/ops/flights/{id}/manifest` | Passenger manifest (CSV/PDF) |
| GET | `/ops/reports/*` | ClickHouse-backed reports (§9.5) |
| GET | `/ops/audit-log?object_type=&object_id=` | Audit trail |

**Analytics collector**

| Method | Path | Purpose |
|---|---|---|
| POST | `/collect` | Batched clickstream events (`sendBeacon`-friendly, `204`, no auth) |

### 7.3 Permission matrix

| Resource | Anon | Traveller | Agency agent | Ops agent | Ticketing | Finance | Superadmin |
|---|---|---|---|---|---|---|---|
| Search / catalog | R | R | R | R | R | R | R |
| Own booking | R* | RW | RW (agency's) | RW | RW | R | RW |
| Any booking | – | – | – | R | RW | R | RW |
| Inventory / schedules | – | – | – | RW | R | – | RW |
| Fares / promos | – | – | – | R | – | RW | RW |
| Refund approval | – | – | – | – | – | RW | RW |
| Void / reissue ticket | – | – | – | – | RW | – | RW |
| Audit log | – | – | – | R | R | R | R |

`R*` = guest retrieval with PNR + last name, rate-limited to 5 attempts / 15 min / IP.

Enforced by DRF permission classes plus **object-level checks in `selectors.py`** — every queryset
for a non-staff actor is filtered by ownership or agency before serialization; there is no
"filter in the view template" path.

### 7.4 Rate limits (Redis token bucket, per IP + per user)

| Scope | Limit |
|---|---|
| `POST /search/flights` | 30 / min anon, 120 / min authed |
| `POST /bookings` | 10 / hour / user, 5 / hour / IP anon |
| `POST /auth/login` | 10 / 15 min / IP, then exponential backoff |
| Guest booking retrieval | 5 / 15 min / IP |
| `POST /collect` | 600 / min / IP (cheap path, 100 events per request max) |
| Global authenticated | 1000 / hour |

---

## 8. Asynchronous processing

### 8.1 Celery configuration

- Broker: `redis://redis:6379/0`. Result backend: `redis://redis:6379/1`, results expire in 1 h.
- `task_acks_late=True`, `worker_prefetch_multiplier=1`, `task_reject_on_worker_lost=True`.
- Serializer: JSON only. `task_time_limit=300`, `task_soft_time_limit=270`.
- Every task is **idempotent** and keyed by a domain id; retries use
  `autoretry_for=(TransientError,)`, `retry_backoff=True`, `retry_jitter=True`, `max_retries=5`.
- Tasks that touch money take a Redis lock (`redis-lock`, key = aggregate id, TTL 60 s) and re-read
  state inside the transaction — the lock is an optimisation, the DB row lock is the guarantee.
- Failed-after-retries tasks land in a `dead_letter` queue and raise an alert.

### 8.2 Queues

| Queue | Workers | Tasks |
|---|---|---|
| `critical` | 4 | `handle_payment_succeeded`, `issue_tickets`, `process_refund`, `release_hold` |
| `default` | 4 | `materialise_schedules`, `recalculate_availability`, imports |
| `notifications` | 2 | email/SMS render + send, PDF generation |
| `analytics` | 2 | `flush_event_buffer`, `rollup_daily_metrics`, `sync_bookings_to_clickhouse` |
| `maintenance` | 1 | cleanup, reconciliation, exports, FX refresh |

### 8.3 Task inventory

| Task | Queue | Trigger |
|---|---|---|
| `booking.release_expired_holds` | critical | beat, 60 s |
| `booking.expire_offers` | default | beat, 5 min |
| `payments.handle_payment_succeeded(event_id)` | critical | webhook |
| `payments.reconcile_pending_payments` | critical | beat, 5 min |
| `payments.process_refund(refund_id)` | critical | on approval |
| `ticketing.issue_tickets(booking_id)` | critical | after confirmation |
| `ticketing.void_expired_unticketed` | critical | beat, 15 min |
| `ops.relay_outbox` | default | beat, 5 s (batch 200) |
| `notifications.send(notification_id)` | notifications | outbox |
| `notifications.send_departure_reminders` | notifications | beat, hourly (T-24 h) |
| `notifications.send_checkin_open` | notifications | beat, hourly (T-48 h) |
| `inventory.materialise_schedules(days=365)` | default | beat, daily 02:00 UTC |
| `inventory.recalculate_availability(flight_id)` | default | on inventory change |
| `inventory.mark_departed_flights` | default | beat, 10 min |
| `ops.detect_disruptions` | default | beat, 5 min |
| `pricing.refresh_exchange_rates` | maintenance | beat, daily 03:00 UTC |
| `pricing.rebuild_calendar_cache` | default | beat, daily 04:00 UTC |
| `analytics.flush_event_buffer` | analytics | beat, 5 s |
| `analytics.sync_bookings_to_clickhouse` | analytics | beat, 5 min (incremental by `updated_at`) |
| `analytics.rollup_daily_metrics(date)` | analytics | beat, daily 01:00 UTC |
| `maintenance.purge_expired_idempotency_keys` | maintenance | beat, daily |
| `maintenance.anonymise_stale_pii` | maintenance | beat, weekly (§12.4) |

### 8.4 Redis usage map

| DB | Use | Key pattern | TTL |
|---|---|---|---|
| 0 | Celery broker | — | — |
| 1 | Celery results | — | 1 h |
| 2 | Django cache | `wf:search:{hash}`, `wf:catalog:airports`, `wf:seatmap:{flight}` | 60 s – 24 h |
| 3 | Locks | `wf:lock:flight:{id}`, `wf:lock:booking:{pnr}` | 60 s |
| 4 | Rate limits | `wf:rl:{scope}:{identity}` | window |
| 5 | Offers | `wf:offer:{offer_id}` | 15 min |
| 6 | Event buffer | Redis Stream `wayfare:events` | trimmed to 1 M |

Cache invalidation: writing inventory or fares for a flight deletes `wf:search:*` entries tagged with
that route via a Redis Set index (`wf:idx:route:{O}:{D}` → set of search keys), so search results
never survive an inventory change by more than the tag-sweep (immediate) or the 60 s TTL.

---

## 9. ClickHouse — logs, clickstream, analytics

### 9.1 Ingestion pipeline

```
Browser  ──POST /collect (batch ≤100, sendBeacon)──┐
Django middleware (api_request_log)  ──────────────┤
Celery task events / domain events  ───────────────┼──▶ Redis Stream `wayfare:events`
Structured app logs (JSON handler)  ────────────────┘            │
                                                                 │  XREADGROUP, batch 5 000
                                            analytics worker ────┘  or 5 s, whichever first
                                                    │
                                    clickhouse-connect client.insert(
                                        table, rows, column_names=[...],
                                        settings={"async_insert": 1,
                                                  "wait_for_async_insert": 0})
```

The stream decouples request latency from ClickHouse availability. If ClickHouse is down, events
accumulate in the stream (capped, oldest trimmed) and the worker retries with backoff; the booking
path is never blocked. Delivery is **at-least-once** — every table is deduplicable by `event_id`
(`ReplacingMergeTree` where dedup matters, and `FINAL`/`argMax` in the reporting queries).

Client-side (`frontend/src/lib/analytics.ts`): events queue in memory, flush on 10 events, 5 s idle,
route change, or `visibilitychange → hidden` via `navigator.sendBeacon`. Respect
`navigator.doNotTrack` and a cookie-consent flag: with analytics consent withheld, only
server-side operational events are recorded, keyed by a session id with no user linkage.

### 9.2 Schemas

```sql
CREATE DATABASE IF NOT EXISTS wayfare;

-- Raw clickstream
CREATE TABLE wayfare.events
(
    event_id      UUID,
    event_time    DateTime64(3, 'UTC'),
    event_name    LowCardinality(String),      -- page_view, search_submitted, offer_viewed,
                                               -- offer_selected, pax_details_completed,
                                               -- payment_started, booking_confirmed, error_shown
    session_id    String,
    anon_id       String,
    user_id       Nullable(UInt64),
    agency_id     Nullable(UInt64),
    page_path     String,
    referrer      String,
    utm_source    LowCardinality(String),
    utm_medium    LowCardinality(String),
    utm_campaign  String,
    device_type   LowCardinality(String),
    browser       LowCardinality(String),
    os            LowCardinality(String),
    country       LowCardinality(String),
    locale        LowCardinality(String),
    search_id     Nullable(UUID),
    offer_id      Nullable(UUID),
    pnr           Nullable(String),
    origin        LowCardinality(String),
    destination   LowCardinality(String),
    depart_date   Nullable(Date),
    cabin         LowCardinality(String),
    pax_count     UInt8,
    amount        Decimal(12, 2),
    currency      LowCardinality(String),
    duration_ms   UInt32,
    props         JSON
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_name, event_time, session_id)
TTL toDateTime(event_time) + INTERVAL 400 DAY
SETTINGS index_granularity = 8192;

-- Search telemetry (one row per executed search)
CREATE TABLE wayfare.search_log
(
    search_id UUID, event_time DateTime64(3,'UTC'), session_id String,
    user_id Nullable(UInt64), origin LowCardinality(String),
    destination LowCardinality(String), depart_date Date,
    return_date Nullable(Date), trip_type LowCardinality(String),
    pax_adults UInt8, pax_children UInt8, pax_infants UInt8,
    cabin LowCardinality(String), currency LowCardinality(String),
    results_count UInt16, cheapest_amount Decimal(12,2),
    median_amount Decimal(12,2), cache_hit UInt8, latency_ms UInt32,
    partial UInt8
)
ENGINE = MergeTree PARTITION BY toYYYYMM(event_time)
ORDER BY (origin, destination, depart_date, event_time)
TTL toDateTime(event_time) + INTERVAL 400 DAY;

-- HTTP access log
CREATE TABLE wayfare.api_request_log
(
    request_id String, ts DateTime64(3,'UTC'), method LowCardinality(String),
    path String, route LowCardinality(String), status UInt16,
    duration_ms UInt32, db_queries UInt16, db_time_ms UInt32,
    user_id Nullable(UInt64), ip IPv6, user_agent String,
    error_code LowCardinality(String)
)
ENGINE = MergeTree PARTITION BY toYYYYMMDD(ts)
ORDER BY (route, ts) TTL toDateTime(ts) + INTERVAL 90 DAY;

-- Application logs
CREATE TABLE wayfare.app_log
(
    ts DateTime64(3,'UTC'), level LowCardinality(String),
    logger LowCardinality(String), service LowCardinality(String),
    message String, request_id String, trace_id String,
    user_id Nullable(UInt64), task_name LowCardinality(String),
    exception String, extra JSON
)
ENGINE = MergeTree PARTITION BY toYYYYMMDD(ts)
ORDER BY (level, service, ts) TTL toDateTime(ts) + INTERVAL 30 DAY;

-- Booking mirror (replicated from Postgres, dedup by booking_id)
CREATE TABLE wayfare.bookings_mirror
(
    booking_id UInt64, pnr String, status LowCardinality(String),
    user_id Nullable(UInt64), agency_id Nullable(UInt64),
    origin LowCardinality(String), destination LowCardinality(String),
    trip_type LowCardinality(String), cabin LowCardinality(String),
    pax_count UInt8, base_amount Decimal(12,2), tax_amount Decimal(12,2),
    ancillary_amount Decimal(12,2), total_amount Decimal(12,2),
    total_amount_usd Decimal(12,2), currency LowCardinality(String),
    source_channel LowCardinality(String), booked_at DateTime('UTC'),
    departure_at DateTime('UTC'), updated_at DateTime('UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(booked_at) ORDER BY (booking_id);

-- Fare price history (for trend charts and fare alerts)
CREATE TABLE wayfare.fare_price_history
(
    captured_at DateTime('UTC'), origin LowCardinality(String),
    destination LowCardinality(String), depart_date Date,
    cabin LowCardinality(String), cheapest_amount Decimal(12,2),
    currency LowCardinality(String), seats_remaining UInt16
)
ENGINE = MergeTree PARTITION BY toYYYYMM(captured_at)
ORDER BY (origin, destination, depart_date, captured_at)
TTL captured_at + INTERVAL 2 YEAR;
```

### 9.3 Materialised views (pre-aggregation)

```sql
CREATE TABLE wayfare.funnel_daily
(
    day Date, step LowCardinality(String), device_type LowCardinality(String),
    sessions AggregateFunction(uniq, String), events AggregateFunction(count)
)
ENGINE = AggregatingMergeTree PARTITION BY toYYYYMM(day)
ORDER BY (day, step, device_type);

CREATE MATERIALIZED VIEW wayfare.funnel_daily_mv TO wayfare.funnel_daily AS
SELECT toDate(event_time) AS day, event_name AS step, device_type,
       uniqState(session_id) AS sessions, countState() AS events
FROM wayfare.events
WHERE event_name IN ('page_view','search_submitted','offer_selected',
                     'pax_details_completed','payment_started','booking_confirmed')
GROUP BY day, step, device_type;

CREATE TABLE wayfare.route_demand_daily
(
    day Date, origin LowCardinality(String), destination LowCardinality(String),
    searches AggregateFunction(count),
    unique_sessions AggregateFunction(uniq, String),
    avg_cheapest AggregateFunction(avg, Decimal(12,2))
)
ENGINE = AggregatingMergeTree PARTITION BY toYYYYMM(day)
ORDER BY (day, origin, destination);

CREATE MATERIALIZED VIEW wayfare.route_demand_daily_mv TO wayfare.route_demand_daily AS
SELECT toDate(event_time) AS day, origin, destination,
       countState() AS searches, uniqState(session_id) AS unique_sessions,
       avgState(cheapest_amount) AS avg_cheapest
FROM wayfare.search_log GROUP BY day, origin, destination;
```

### 9.4 Event taxonomy (contract for the frontend)

`page_view`, `search_submitted`, `search_results_rendered`, `filter_applied`, `sort_changed`,
`offer_viewed`, `offer_selected`, `pax_details_started`, `pax_details_completed`,
`ancillary_added`, `ancillary_removed`, `seat_selected`, `payment_started`, `payment_failed`,
`booking_confirmed`, `checkin_started`, `checkin_completed`, `error_shown`, `api_latency`.

Names are `snake_case`, past tense, defined once in `frontend/src/lib/events.ts` as a typed union;
adding an event requires extending that union, so untyped ad-hoc names cannot ship.

### 9.5 Reports exposed via `/ops/reports/*`

| Report | Source | Content |
|---|---|---|
| `funnel` | `funnel_daily` | Step-by-step conversion, by device and date range |
| `search-conversion` | `search_log` + `bookings_mirror` | Look-to-book by route |
| `revenue` | `bookings_mirror` | Revenue by day/route/cabin/channel, USD-normalised |
| `load-factor` | Postgres + mirror | Seats sold ÷ capacity by flight and departure date |
| `top-routes` | `route_demand_daily` | Demand vs. sales |
| `abandonment` | `events` | Sessions reaching payment without confirmation, with last error |
| `api-health` | `api_request_log` | p50/p95/p99 latency and error rate by route |
| `fare-trend` | `fare_price_history` | Price movement for a route/date |

All report endpoints are cached in Redis for 5 minutes, accept `date_from`/`date_to` (max 400-day
span), and stream CSV when `Accept: text/csv`.

---

## 10. Frontend

### 10.1 Structure

Vite + React 19 + TypeScript, Tailwind v4 via `@tailwindcss/vite` (`@import "tailwindcss";` in
`src/index.css`; design tokens declared with `@theme`). Three route trees behind one bundle, split by
`React.lazy`: storefront, agency console, ops console.

```
/                              landing + search widget
/search                        results (filters, sort, matrix)
/booking/:offerId/passengers   passenger + contact details
/booking/:pnr/extras           seats, bags, meals
/booking/:pnr/payment          payment + 3DS
/booking/:pnr/confirmation     PNR, e-ticket, add-to-calendar
/manage                        find booking (PNR + last name)
/manage/:pnr                   view, change, cancel, refund status
/checkin                       check-in entry
/checkin/:pnr                  passenger/segment selection → boarding pass
/account/*                     profile, travellers, bookings
/agency/*                      dashboard, bookings, credit, users
/ops/*                         flights, inventory, fares, PNRs, refunds, reports, audit
```

### 10.2 State and data

- **Server state:** TanStack Query. Search results `staleTime` 60 s; booking details `staleTime` 0
  with a 5 s `refetchInterval` while status is `PENDING_TICKETING`. Mutations invalidate by key.
- **Client state:** Zustand for the booking wizard (selected offer, passenger draft, extras cart,
  currency), persisted to `sessionStorage` so a refresh mid-flow does not lose progress.
- **Forms:** react-hook-form + zod; the zod schemas are generated from the OpenAPI schema where
  possible so client and server validation cannot drift.
- **API client:** `openapi-typescript` types + a thin fetch wrapper handling auth refresh (single
  in-flight refresh, queued retries), `Idempotency-Key` generation, and problem-detail parsing.

### 10.3 Key UI components

`FlightSearchForm` (airport typeahead with debounce + recent searches), `DatePickerWithFares`
(calendar showing cheapest fare per day), `FlightCard`, `FareFamilySelector` (comparison grid),
`ItineraryTimeline`, `PriceBreakdown` (expandable base/tax/fee/ancillary), `SeatMap` (SVG, zoom, per-
seat pricing, keyboard-navigable), `PassengerForm` (per-pax-type validation), `AncillaryPicker`,
`PaymentPanel` (provider SDK mount + 3DS), `BookingStatusStepper`, `BoardingPassCard`,
`InventoryGrid` (ops, editable RBD authorisations), `RefundQueueTable`, `ReportChart`.

### 10.4 UX rules

- Prices always render with currency and, if converted, the original currency in a tooltip.
- Every hold shows a live countdown; at T-2 min a modal offers extension (one extension, +10 min).
- Search results stream in progressively; skeleton rows, never a blank screen.
- All flows are keyboard-operable; seat map and calendar have list-based fallbacks.
- WCAG 2.2 AA: contrast ≥ 4.5:1, visible focus rings, `aria-live` for price and availability changes,
  no colour-only status encoding.
- Errors from the API render the problem-detail `title` + field errors inline, never a raw stack.
- Dark mode via `prefers-color-scheme` plus a manual toggle, both driven by CSS variables.

---

## 11. Docker Compose

### 11.1 Services

| Service | Image / build | Ports | Depends on | Notes |
|---|---|---|---|---|
| `postgres` | `postgres:18-alpine` | 5432 | — | volume `pgdata`, healthcheck `pg_isready` |
| `redis` | `redis:8-alpine` | 6379 | — | `--appendonly yes`, volume `redisdata` |
| `clickhouse` | `clickhouse/clickhouse-server:25.8` | 8123, 9000 | — | volume `chdata`, `ops/clickhouse/config.d` |
| `api` | `./backend` | 8000 | pg, redis, ch | dev: `runserver`; prod: gunicorn+uvicorn workers |
| `worker-critical` | `./backend` | — | api deps | `celery -A config worker -Q critical -c 4` |
| `worker-default` | `./backend` | — | api deps | `-Q default,maintenance -c 4` |
| `worker-notify` | `./backend` | — | api deps | `-Q notifications -c 2` |
| `worker-analytics` | `./backend` | — | api deps | `-Q analytics -c 2` |
| `beat` | `./backend` | — | api deps | `celery -A config beat -S django` |
| `flower` | `mher/flower` | 5555 | redis | dev only |
| `web` | `./frontend` | 5173 | api | dev: Vite HMR; prod: build → nginx |
| `nginx` | `nginx:alpine` | 80 | api, web | routes `/api`,`/admin`,`/static` → api; `/` → SPA |
| `mailpit` | `axllent/mailpit` | 8025 | — | dev SMTP sink |

`migrate` runs as a one-shot service (`depends_on: postgres: condition: service_healthy`) executing
`python manage.py migrate && python manage.py ch_migrate && python manage.py collectstatic --noinput`;
`api` depends on it completing successfully. ClickHouse DDL lives in `backend/clickhouse/migrations/`
and is applied by a custom `ch_migrate` management command that tracks applied files in a
`wayfare.schema_migrations` table.

### 11.2 Environment (`.env.example`)

```env
# Django
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=change-me
DEBUG=1
ALLOWED_HOSTS=localhost,127.0.0.1,api
CORS_ALLOWED_ORIGINS=http://localhost:5173
# Postgres
POSTGRES_DB=wayfare
POSTGRES_USER=wayfare
POSTGRES_PASSWORD=wayfare
DATABASE_URL=postgres://wayfare:wayfare@postgres:5432/wayfare
# Redis
REDIS_URL=redis://redis:6379
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
# ClickHouse
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=wayfare
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_ASYNC_INSERT=1
# Payments
PAYMENT_PROVIDER=sandbox            # sandbox | stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
# Booking rules
HOLD_TTL_MINUTES=20
OFFER_TTL_MINUTES=15
CHECKIN_OPEN_HOURS=48
CHECKIN_CLOSE_MINUTES=60
REFUND_AUTO_APPROVE_LIMIT=500
DEFAULT_CURRENCY=USD
# Email
EMAIL_HOST=mailpit
EMAIL_PORT=1025
DEFAULT_FROM_EMAIL=noreply@wayfare.local
# Frontend
VITE_API_BASE_URL=http://localhost/api/v1
VITE_PAYMENT_PUBLIC_KEY=
VITE_ANALYTICS_ENABLED=1
```

### 11.3 Makefile targets

```
make up            # build + start the stack
make down          # stop (keep volumes);  make clean  drops volumes
make logs s=api    # tail one service
make migrate       # Django + ClickHouse migrations
make seed          # demo data: 16 airports, 4 airlines, 90 days of flights, fares, users
make test          # backend pytest + frontend vitest
make e2e           # Playwright against the compose stack
make lint          # ruff + mypy + eslint + tsc + prettier
make schema        # regenerate OpenAPI + frontend types
make shell         # Django shell_plus
make psql / chcli  # database consoles
```

`make seed` must produce a stack a new developer can book on end-to-end within one command:
sample airports, aircraft, seat maps, 90 days of materialised flights, fare families and fares,
one traveller (`demo@wayfare.local`), one agency, one ops user, and the sandbox payment provider.

---

## 12. Security & compliance

### 12.1 Authentication

JWT with short access tokens and rotating refresh tokens (blacklist on rotation and logout).
Argon2 password hashing. Optional TOTP MFA, **mandatory for `OPS_*`, `TICKETING`, `FINANCE`,
`SUPERADMIN`**. Login throttling with progressive delay and account lock after 10 failures in
15 minutes. Password reset tokens are single-use, 30-minute TTL, and invalidate active sessions.

### 12.2 Authorisation

Role + scope checks in DRF permission classes, object-level ownership filtering in `selectors.py`,
and a deny-by-default `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` with explicit
`AllowAny` opt-ins. Staff endpoints live under `/ops/` with a dedicated permission base class so a
missing decorator fails closed.

### 12.3 Transport & application hardening

HTTPS only in production (HSTS 1 year, preload), `SECURE_SSL_REDIRECT`, secure + `HttpOnly` +
`SameSite=Lax` cookies, CSRF for session-authenticated admin, strict CORS allowlist, CSP with no
inline scripts (hashes for the payment SDK), `X-Content-Type-Options`, `Referrer-Policy:
strict-origin-when-cross-origin`. Webhook endpoints verify provider signatures with constant-time
comparison and reject events older than 5 minutes. All SQL goes through the ORM or parameterised
queries — string-interpolated SQL is a review blocker, in ClickHouse queries too.

### 12.4 Data protection

- **PCI:** SAQ-A. Card data never touches Wayfare servers or logs; only brand + last4 + provider
  token are stored.
- **PII:** passenger documents (`doc_number`) encrypted at rest with a Fernet key from the
  environment (rotatable, key id stored alongside the ciphertext). PII is redacted in logs by a
  logging filter with a field allowlist — the log path is opt-in, not opt-out.
- **Retention:** APIS/travel-document data purged 90 days after the last flown segment; bookings
  anonymised 7 years after completion (tax retention); analytics events TTL'd per §9.2.
- **GDPR:** `GET /me/export` produces a JSON+CSV archive; `POST /me/delete` anonymises the user and
  detaches bookings from personal identity while retaining financial records.
- **Audit:** every staff mutation writes `AuditLog` with before/after diffs; the log is append-only
  (no update/delete permission for the app DB role).

---

## 13. Observability

- **Structured logging:** `structlog` JSON to stdout, with `request_id` (from `X-Request-ID` or
  generated), `trace_id`, `user_id`, `pnr` bound into the context. A `ClickHouseLogHandler` mirrors
  `WARNING+` (and all of `wayfare.*` at `INFO`) into the event stream — never synchronously.
- **Metrics:** `django-prometheus` at `/metrics` (protected). Beyond RED metrics, business gauges:
  `wayfare_bookings_created_total{status}`, `wayfare_hold_expired_total`,
  `wayfare_payment_failures_total{code}`, `wayfare_ticket_issue_latency_seconds`,
  `wayfare_search_latency_seconds`, `wayfare_outbox_backlog`, `wayfare_event_stream_lag`.
- **Tracing:** OpenTelemetry instrumentation for Django, psycopg, redis, celery; OTLP exporter,
  disabled by default in dev.
- **Health:** `/healthz` (process), `/readyz` (Postgres, Redis, ClickHouse round-trips, with per-
  dependency status), `/api/v1/version` (git sha, build time).
- **Alerts (thresholds to wire into whatever monitor is used):** outbox backlog > 1 000 for 5 min;
  event-stream lag > 60 s; payment failure rate > 5% over 15 min; ticket issuance p95 > 30 s; any
  `dead_letter` arrival; `readyz` failing 2 consecutive checks.

---

## 14. Testing

| Layer | Tooling | Bar |
|---|---|---|
| Unit — domain services | pytest, factory_boy, freezegun | ≥ 90% on `services/`, `pricing/`, `ticketing/` |
| Integration — API | pytest-django + DRF `APIClient`, real Postgres/Redis | Every endpoint: happy, auth-denied, validation, conflict |
| Contract | schemathesis against `/api/schema/` | No 500s, schema conformance |
| Concurrency | pytest + threads/`pytest-xdist` | Overselling is impossible under N parallel bookings on 1 seat |
| ClickHouse | pytest against a compose CH instance | DDL applies; MV rollups match raw aggregates |
| Frontend unit | Vitest + Testing Library | Components, hooks, money/date formatting |
| E2E | Playwright | Search→book→pay→ticket; change; cancel+refund; check-in; ops refund approval |
| Load | Locust | 200 rps search, 20 rps booking; p95 targets in §15 |
| Security | `pip-audit`, `npm audit`, bandit, ZAP baseline | No high/critical in CI |

Non-negotiable test cases:

1. Two concurrent bookings for the last seat: exactly one succeeds, the other gets `409`.
2. Duplicate webhook delivery charges once and issues one ticket set.
3. Hold expiry returns inventory exactly once, even if the task runs twice.
4. Replayed `Idempotency-Key` returns the original response without a second charge.
5. Infant-without-adult, expired document, and past-date searches are rejected with field errors.
6. Refund penalty computation matches the fare family ladder at each time-to-departure boundary.
7. Ticket number check digit validates; conjunction tickets link correctly on exchange.
8. A guest cannot retrieve another PNR by brute force (rate limit + last-name match).

CI (GitHub Actions): lint → type-check → backend tests (services matrix) → frontend tests → build
images → e2e on compose → security scans. Merges blocked on all green.

---

## 15. Non-functional requirements

| Attribute | Target |
|---|---|
| Search latency | p50 < 300 ms, p95 < 800 ms (cached: p95 < 120 ms) |
| Booking create | p95 < 1.5 s |
| Ticket issuance | 95% within 30 s of payment capture |
| API availability | 99.9% monthly (booking + payment paths) |
| Throughput (single compose host) | 200 rps search, 20 rps booking |
| Data durability | Postgres PITR, nightly base backup, 30-day retention; ClickHouse best-effort |
| RPO / RTO | 5 min / 1 h |
| Correctness | Zero oversell; ledger balances to payments to the cent |
| Accessibility | WCAG 2.2 AA |
| i18n | UI strings externalised (en, bn seed locales); UTC storage, local rendering |
| Browser support | Last 2 versions of Chrome, Firefox, Safari, Edge |

---

## 16. Delivery plan

| Milestone | Deliverable | Exit criteria |
|---|---|---|
| **M0 — Foundation** | Compose stack, Django+DRF skeleton, Vite SPA shell, CI, OpenAPI pipeline | `make up` serves the SPA and `/api/docs`; CI green |
| **M1 — Catalog & inventory** | Reference data, schedules, flight materialisation, cabins/RBDs, seat maps, ops CRUD, `make seed` | 90 days of flights seeded; inventory editable in the ops console |
| **M2 — Search & pricing** | Fares, taxes, promos, connection builder, quote engine, Redis caching, search UI | Round-trip search returns priced, signed offers within the latency budget |
| **M3 — Booking core** | Offers, holds, PNRs, passengers, ancillaries, seats, state machine, hold expiry | Concurrency tests pass; no oversell under load |
| **M4 — Payments & ticketing** | Provider abstraction, sandbox + Stripe, webhooks, ledger, e-tickets, coupons, EMDs, itinerary PDF | End-to-end book→pay→ticket in E2E suite |
| **M5 — Servicing** | Cancel, refund ladder + approval queue, change/exchange, void, agency credit | Refund and exchange E2E flows; ledger reconciles |
| **M6 — Check-in & disruption** | Check-in, boarding passes, disruption detection, rebooking, notifications | Boarding pass PDF with valid BCBP; disruption fan-out under 5 min |
| **M7 — Analytics** | Collector, event stream, ClickHouse schemas + MVs, mirror sync, ops reports | Funnel, revenue, load-factor, api-health reports live |
| **M8 — Hardening** | MFA, CSP, PII encryption, GDPR export/delete, load + security testing, runbooks | NFR targets met; no high/critical findings |

Each milestone ships migrations, tests, updated OpenAPI, and a section in the README runbook.

---

## 17. Decisions and open questions

### Decisions taken in this spec

1. **Own inventory, not GDS passthrough** — keeps the system self-contained and testable; external
   supply arrives later behind `SupplierAdapter`.
2. **Postgres for truth, ClickHouse for analysis** — no dual-write on the booking path; ClickHouse
   is fed asynchronously and is allowed to lag or be rebuilt from the mirror sync.
3. **Redis Stream buffer instead of Kafka** — one fewer service in compose; the interface
   (produce → consumer group → batch insert) is Kafka-shaped if volume later demands it.
4. **Signed, expiring offers** — makes search stateless and cacheable while keeping the booking step
   tamper-proof, without holding inventory during browsing.
5. **Nested cabin + RBD inventory** — mirrors real revenue management (authorisations may exceed
   cabin capacity; the cabin is the hard ceiling), and makes fare-ladder pricing meaningful.
6. **SAQ-A payments** — the SPA talks to the provider directly; Wayfare never sees a PAN.
7. **Transactional outbox for all side effects** — email, webhooks, and analytics can never roll a
   booking back or block its commit.

### Open questions for the product owner

1. **Currency of record:** settle in a single base currency (USD) with display conversion, or price
   natively per point of sale? The spec assumes the former (`total_amount_usd` in the mirror).
2. **Oversell policy:** is `oversell_allowance` used at all in v1, and who authorises denied-boarding
   compensation? Currently defaults to 0.
3. **Agency commission model:** net fares vs. commission on published fares — the schema carries
   `commission_pct` but no settlement/invoicing flow is specified.
4. **SMS provider and jurisdictions** — needed before the notification channel leaves stub state.
5. **Baggage rules depth:** simple per-fare-family allowance (assumed) vs. full piece/weight concept
   with route-specific overrides.
6. **Hold TTL for agencies:** travellers get 20 minutes; agencies often expect 24–72 h option
   holds. If required, this changes the inventory-lock model and needs a separate queue.
