---
name: new-endpoint
description: Add a DRF endpoint end-to-end — serializer, view, URL, permissions, selector, tests, OpenAPI regeneration, and the generated frontend hook. Use when adding or changing any route under /api/v1.
---

# New endpoint

Authority: [api-conventions.md](../../references/api-conventions.md).

## Steps

1. **Place it.** Traveller/agency routes under `/api/v1/<resource>`, staff routes under
   `/api/v1/ops/<resource>` inheriting `OpsPermission`. Booking-scoped actions nest:
   `/bookings/{pnr}/<action>`.

2. **Selector before view.** Add or reuse a function in `selectors.py` that returns the queryset
   already filtered for the actor. The view must never call `Model.objects.all()`.

3. **Serializer.** Money through `MoneyField` (`{amount, currency}`, decimal string). Expose
   `public_id`, never integer PKs. Read-only fields explicit. No DB queries for authorisation here.

4. **View.** Validate → call a service → serialize. No domain logic. For mutations:
   - `@idempotent(scope="<scope>")` if it creates money or inventory effects
   - `If-Match` / `ETag` on booking mutations
   - throttle scope registered in settings (see SPEC.md §7.4)

5. **Errors.** Raise domain exceptions from `apps.common.exceptions`; do not build responses by
   hand. Check the status/code table in the reference and add a new `code` there if you invent one.

6. **Tests — four minimum:** happy path, auth-denied, validation (422 with field errors), conflict
   (409). Plus `assertNumQueries` on any list endpoint.

7. **Regenerate the contract.**
   ```bash
   make schema
   ```
   This updates `/api/schema/` output and `frontend/src/api/schema.d.ts`. CI fails if the committed
   schema differs from the generated one.

8. **Frontend hook.** Add a query-key factory entry in `src/api/keys.ts` and a hook in the owning
   feature. Never hand-write request/response types — import from the generated schema.

9. **Verify.**
   ```bash
   make lint && make test && make schema
   ```

## Checklist

- [ ] Ownership filtering in the selector, not the view
- [ ] Permission class explicit; `AllowAny` justified in a comment if used
- [ ] Money serialized as `{amount, currency}` decimal strings
- [ ] Idempotency + `If-Match` where the endpoint mutates money or inventory
- [ ] RFC 9457 problem details, correct status/code pair
- [ ] Four tests present; list endpoints assert query counts
- [ ] `make schema` run and the diff committed
