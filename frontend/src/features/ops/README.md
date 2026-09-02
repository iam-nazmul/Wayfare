# features/ops

The staff console: reports, the refund approval queue, and open disruptions.

## Responsibilities

- Owns: the ops shell and its three pages.
- Does not own: authorisation. The client gate hides the console; every `/ops` endpoint checks
  the role server-side regardless of what is rendered.
- Not built: flight and inventory editing, PNR search, and the audit log — the endpoints exist
  for flights and schedules, but no screens have been written for them yet.

## Key objects

| Object | Role |
|---|---|
| [OpsLayout.tsx](OpsLayout.tsx) | Tabbed shell; redirects non-staff to sign in |
| [ReportsPage.tsx](ReportsPage.tsx) | All eight report slugs, date window, CSV download |
| [RefundQueuePage.tsx](RefundQueuePage.tsx) | Approve or reject queued refunds |
| [DisruptionsPage.tsx](DisruptionsPage.tsx) | Open disruptions, refreshed every minute |
| [api.ts](api.ts) `useReport` | `staleTime` matched to the server's 5-minute cache |

## Invariants

- **The gate is cosmetic, the server is authoritative.** `isStaff` decides what to render; a
  traveller who types the URL gets 403s from the API either way.
- **Only finance decides refunds.** The approve and reject buttons are hidden without the role,
  and the endpoint enforces it — the hidden buttons are courtesy, not security.
- **Reports are read-only.** Nothing in this console mutates a booking; refund decisions are the
  single exception and go through the refund endpoints.
- **Report queries are not re-run needlessly.** The server caches for five minutes and the client
  matches that `staleTime`; refetching sooner re-reads the same answer.

## Entry points

- `/ops/reports` · `/ops/refunds` · `/ops/disruptions`, all behind `/ops` and staff-gated.

## Gotchas

- CSV cannot be a plain link: the endpoint needs a bearer token, so the page fetches with the
  token attached and hands the browser a blob.
- The 400-day window cap is enforced server-side and comes back as a 422 with a field error —
  render it rather than treating it as a failure.
- `load-factor` reads live Postgres inventory, not the ClickHouse mirror, so it can be slower
  than the other reports on a wide window.
- Report columns come from the query, not a fixed type. The table renders whatever it is given;
  do not hard-code column names in the page.

## Testing

    make test-fe

Required: the queue lists refunds and posts approve/reject with the note; the decision buttons
are hidden without the finance role; a signed-out visitor is redirected instead of seeing the
console.
