# API conventions

Contract for everything under `/api/v1`. Authority: [SPEC.md](../../SPEC.md) §7.

## Identifiers

Expose `public_id` (UUIDv7). Never expose integer PKs. Bookings are addressed by `pnr`
(6 chars, `ABCDEFGHJKLMNPQRSTUVWXYZ0123456789`, no I/O), tickets by `ticket_number`.

## Money

Always an object, never a bare number. Decimal string, never float.

```json
{ "total": {"amount": "412.50", "currency": "USD"} }
```

Serializer: `MoneyField` from `apps.common.fields` — emits `{amount, currency}`, parses to a
`Money` value object. `DecimalField(max_digits=12, decimal_places=2)` on models.

## Pagination

Cursor-based. `?cursor=&page_size=` (default 20, max 100).

```json
{ "results": [], "next": "cD0yMDI2…", "previous": null }
```

Use `CursorPagination` with a stable `ordering` — never offset pagination on tables that receive
concurrent inserts (search results, bookings, events).

## Errors — RFC 9457

One shared handler in `apps/common/exceptions.py`. Never leak stack traces or ORM messages.

```json
{ "type": "https://wayfare.dev/errors/inventory-unavailable",
  "title": "Requested seats are no longer available",
  "status": 409,
  "detail": "Only 1 seat remains in class Q on WF120",
  "code": "inventory_unavailable",
  "request_id": "01J8…",
  "errors": [{"field": "passengers", "message": "Exceeds available seats"}] }
```

| Situation | Status | `code` |
|---|---|---|
| Field validation | 422 | `validation_error` |
| Unauthenticated | 401 | `authentication_required` |
| Authenticated, not permitted | 403 | `permission_denied` |
| Not found / not owned | 404 | `not_found` |
| Offer expired | 409 | `offer_expired` |
| Seats gone between offer and book | 409 | `inventory_unavailable` |
| Illegal state transition | 409 | `invalid_transition` |
| `ETag` mismatch | 412 | `precondition_failed` |
| Idempotency key reused with a different body | 422 | `idempotency_key_reuse` |
| Rate limited | 429 | `rate_limited` (+ `Retry-After`) |

Returning 404 rather than 403 for objects the caller does not own is deliberate — it does not
confirm existence.

## Idempotency

Required on `POST /bookings`, `/payment-intents`, `/refunds`, `/checkins`.

- Client sends `Idempotency-Key: <uuid>`.
- Server stores `(scope, key, request_hash, response_status, response_body)`.
- Same key + same body hash → replay the stored response, do not re-execute.
- Same key + different body hash → 422 `idempotency_key_reuse`.
- Keys expire after 24 h (`purge_expired_idempotency_keys`).

Decorate with `@idempotent(scope="booking_create")` from `apps.common.idempotency`.

## Concurrency

Booking mutations return an `ETag` derived from `Booking.version`. Mutations accept `If-Match`;
mismatch → 412. `version` is bumped with `F("version") + 1` inside the transaction.

## Auth

`Authorization: Bearer <access>`. Access 15 min, refresh 7 d rotated with blacklist, refresh stored
in an `HttpOnly; Secure; SameSite=Lax` cookie. Guest booking retrieval needs `pnr` + `last_name`
and is rate-limited 5 / 15 min / IP.

## Permissions

`DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`. `AllowAny` is always explicit and always
justified in a comment. Staff endpoints live under `/ops/` and inherit `OpsPermission`, so a
forgotten permission class fails closed rather than open.

Object-level access is enforced by **filtering the queryset in `selectors.py`**, not by checking in
the view. A view that calls `Model.objects.all()` is a bug.

## Versioning

URL major version. Inside a version: additive only — new optional fields, new endpoints. Removing
a field, tightening validation, or changing a status code needs `/api/v2`.

## Schema

`drf-spectacular` at `/api/schema/`, docs at `/api/docs/`. The schema is the contract: after any
serializer, view, or URL change run `make schema` to regenerate frontend types. CI fails if the
committed schema differs from the generated one.
