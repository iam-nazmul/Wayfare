# features/payment

The card step between a held PNR and a ticketed one, plus the polling that waits for the
provider's callback to land.

## Responsibilities

- Owns: the payment page, the intent hooks, and the booking-status polling that decides when the
  traveller is done.
- Does not own: the booking itself (`features/booking`), or how tickets render — the confirmation
  page reads `useTickets` from here.

## Key objects

| Object | Role |
|---|---|
| [api.ts](api.ts) `useCreateIntent` | `POST /payment-intents`, always with an `Idempotency-Key` |
| [api.ts](api.ts) `useConfirmIntent` | Sandbox stand-in for the provider's browser SDK |
| [api.ts](api.ts) `useBookingStatus` | Polls the booking every 2 s until it is ticketed |
| [api.ts](api.ts) `useTickets` | E-tickets and coupon status, once issued |
| [PaymentPage.tsx](PaymentPage.tsx) | Amount due, card form, hold countdown, waiting state |

## Invariants

- **The booking is the source of truth, not the intent.** The webhook decides the outcome and may
  land after this page has asked, so success is "the booking says TICKETED", never "the confirm
  call returned 202".
- **Polling stops when it should.** `refetchInterval` returns `false` once the booking is
  `TICKETED` or `CONFIRMED`; an unbounded 2-second poll is a self-inflicted load test.
- **Card data goes to the provider, not to us.** With a real PSP the number never touches this
  origin. The sandbox endpoint mirrors that shape so the surrounding code does not change.
- **A decline is recoverable.** The hold survives, so the form stays usable for another card
  rather than sending the traveller back to search.

## Entry points

- Route `/booking/:pnr/pay` — reached from the passenger form, or from the Pay button on a held
  booking's confirmation page.
- On success it returns to `/booking/:pnr`, which renders the ticketed view.

## Gotchas

- The sandbox test cards are listed on the page and clickable — `4242…` succeeds, `4000…0002`
  declines, `4000…3220` returns `REQUIRES_ACTION`.
- 3-D Secure has no challenge UI. The page says so rather than hanging on a state it cannot
  advance.
- `state.lastName` carries guest access from the previous page. Without it a signed-out traveller
  who reloads cannot read their own booking, which is why the page falls back to the surname on
  the booking it already has.
- The hold countdown is the real deadline: once it expires the seats are gone and paying is
  refused by the API, so the submit button disables itself.

## Testing

    make test-fe

Required: the amount due renders from `balance_due`; a decline keeps the form usable; polling
stops once the booking is ticketed.
