# features/manage

Everything a traveller does with a booking after it exists: view it, pay the balance, change the
flight, cancel it, or take a replacement after a disruption.

## Responsibilities

- Owns: booking retrieval by PNR + surname, and the cancel / change / rebook panels.
- Does not own: the payment form (`features/payment`), search (`features/search`), or the
  post-booking confirmation immediately after checkout (`features/booking`).
- Not built: check-in and seat selection — those endpoints do not exist yet.

## Key objects

| Object | Role |
|---|---|
| [store.ts](store.ts) `useManageAccess` | Surname per PNR, in sessionStorage — guest calls need it every time |
| [api.ts](api.ts) `useManagedBooking` | Polls while `PENDING_TICKETING`, stops when it settles |
| [api.ts](api.ts) `useCancelBooking` | Quote-only and real cancellation, both idempotent |
| [ManageBookingPage.tsx](ManageBookingPage.tsx) | Status, itinerary, tickets, payments, refunds |
| [CancelPanel.tsx](CancelPanel.tsx) | Shows the penalty before it will cancel anything |
| [ChangePanel.tsx](ChangePanel.tsx) | Search → quote → confirm, paying any delta |
| [RebookPanel.tsx](RebookPanel.tsx) | Disruption alternatives, shown only when offered |

## Invariants

- **The surname travels with every guest call.** Losing it turns the next request into a 404, so
  it is stored per PNR for the session rather than re-asked at each step.
- **A cancellation is quoted before it happens.** `quote_only` shows the penalty and what comes
  back; nothing is cancelled until the traveller confirms the figure they were shown.
- **Servicing mutations are idempotent.** Cancel, change-confirm and rebook all send an
  `Idempotency-Key`; a double-click must not raise two refunds or take two seats.
- **Every servicing action invalidates the whole booking.** Money, coupons and seats all move
  together, so the page refetches booking, tickets, payments, refunds and options as one.
- **Actions are gated on status.** Cancel and change only render for states the API accepts, so
  the UI never offers a button that is guaranteed to 409.

## Entry points

- `/manage` — find a booking by reference and surname
- `/manage/:pnr` — view and service it

## Gotchas

- Poll only while `PENDING_TICKETING`. An unbounded `refetchInterval` on a settled booking is a
  self-inflicted load test.
- A same-day cancellation is a **void**: full refund, no penalty. The quote and the cancellation
  come from one server-side function, so the number shown is the number paid — do not compute a
  penalty client-side.
- A change with nothing to pay completes immediately; one with a delta redirects to the payment
  page, and the reissue happens after capture. Both end on `TICKETED`.
- Rebooking options hold no seats. They can 409 on acceptance, which the panel surfaces rather
  than swallowing.

## Testing

    make test-fe

Required: the surname is on every call; the cancel quote renders before cancelling; a disrupted
booking offers alternatives; a refunded booking offers no actions; a missing booking explains
itself rather than showing an empty page.
