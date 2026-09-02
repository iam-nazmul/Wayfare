# features/booking

The wizard between a chosen offer and a held PNR: passenger details, contact, and the
confirmation that shows the booking reference.

## Responsibilities

- Owns: the passenger-details form, the confirmation view, and the wizard's client state.
- Will own (later): seat selection, ancillaries, and payment.
- Does not own: search or the flight cards (`features/search`), or money and date formatting
  (`lib/money.ts`, `lib/dates.ts`).

## Key objects

| Object | Role |
|---|---|
| [store.ts](store.ts) `useBookingWizard` | Selected offer + party, persisted to sessionStorage |
| [api.ts](api.ts) `useCreateBooking` | `POST /bookings`, always with an `Idempotency-Key` |
| [api.ts](api.ts) `useBooking` | `GET /bookings/{pnr}`, with `last_name` for guests |
| [PassengerDetailsPage.tsx](PassengerDetailsPage.tsx) | One fieldset per seated passenger, plus contact |
| [BookingConfirmationPage.tsx](BookingConfirmationPage.tsx) | PNR, hold countdown, itinerary, price |

## Invariants

- **Every create carries an `Idempotency-Key`.** `api.post(..., { idempotent: true })` mints one;
  a double-submitted form must not hold seats twice.
- **The offer's expiry is visible and enforced.** The submit button is disabled once the 15-minute
  price window closes, rather than letting the traveller fill a form that will 409.
- **The wizard is client state, the booking is server state.** The offer lives in Zustand
  (sessionStorage, so a reload does not lose it); the booking is a TanStack Query resource.
- **Money is never re-computed here.** Totals render through `formatMoney` from the API's decimal
  strings; parsing them to `Number` for arithmetic reintroduces the float bug the API avoids.

## Entry points

- Route `/book` — reached from the Select button on a flight card.
- Route `/booking/:pnr` — after a create it renders from router state; opened cold it fetches with
  the surname from `location.state`, so a bookmarked link without one shows the retrieval message.

## Gotchas

- The store is `sessionStorage`, so a fresh tab has no offer and the page sends the traveller back
  to search. That is the intended behaviour — an offer is only valid for 15 minutes anyway.
- One row is rendered per *seated* passenger. Infants are part of the party but ride on an adult's
  lap; the API pairs each with an adult by position.
- The API validates passenger type against date of birth at the return date, so a wrong DOB comes
  back as a 422 keyed by passenger index, not by a named field.
- A hold that has expired still renders — the confirmation says so rather than 404ing, because the
  traveller needs to understand what happened to the seats.

## Testing

    make test-fe

Required: no offer in the store sends the traveller back to search; one form per seated passenger;
submit posts the typed payload with `idempotent: true` and navigates to the PNR; an expired offer
disables submit.
