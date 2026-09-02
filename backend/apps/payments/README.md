# payments

Money in and out: provider intents, captured payments, the append-only ledger, and the webhook
intake that turns a held booking into a sold one.

## Responsibilities

- Owns: `PaymentIntent`, `Payment`, `Refund`, `LedgerEntry`, `ProviderWebhookEvent`, and the
  provider abstraction.
- Owns the moment a hold becomes a sale — it calls `inventory.availability.confirm`, moves the
  booking to `PENDING_TICKETING`, and dispatches ticketing.
- Does not own: seat counts (`apps.inventory`), booking status rules (`booking/services/state.py`),
  or ticket issuance (`apps.ticketing`).
- Not built yet: refund processing (`payments.process_refund`), agency credit, Stripe.

## Key objects

| Object | Role |
|---|---|
| [providers/base.py](providers/base.py) `PaymentProvider` | The Protocol every provider implements (SPEC.md §5.7) |
| [providers/sandbox.py](providers/sandbox.py) `SandboxProvider` | Deterministic outcomes keyed off the test card |
| [services/intents.py](services/intents.py) `create_payment_intent` | Opens an intent for the outstanding balance |
| [services/webhooks.py](services/webhooks.py) `record_event` | Verify, store once, return `None` on a replay |
| [services/confirm.py](services/confirm.py) `apply_successful_payment` | The money-touching transaction |
| [tasks.py](tasks.py) `handle_payment_succeeded` | Applies one callback under the booking lock |

## Invariants

- **No card data, ever.** No PAN or CVV reaches a model, a log, or a fixture — brand, last four
  and the provider token only. The sandbox confirm endpoint takes a test number to choose an
  outcome and drops it before anything is written.
- **`provider_event_id` is the deduplication.** Webhooks arrive out of order and more than once;
  the unique constraint decides, not a prior `SELECT` that would still race.
- **Applying a payment is idempotent on `charge_id`.** A redelivered success must not sell the
  seats twice — `apply_successful_payment` returns the existing `Payment` instead.
- **Payment and inventory move in one transaction.** A recorded payment whose hold never became a
  sale would oversell the flight on the next search.
- **A payment that lands after the hold is gone is refunded, never kept.** If the booking is no
  longer `HELD`, the seats stay released, a `Refund` is queued and `payment_requires_refund` goes
  to the outbox. Silently keeping the money is the worst available outcome.
- **The ledger is append-only.** Rows are never updated or deleted, and the admin enforces it.
- **Confirmation does not depend on the webhook.** `reconcile_pending_payments` re-dispatches any
  verified event still unprocessed after 3 minutes; the client polls the booking.

## Entry points

- `POST /api/v1/bookings/{pnr}/payment-intents` — `Idempotency-Key` required, `payment` throttle
- `GET /api/v1/bookings/{pnr}/payment-intents/{id}` — poll one intent
- `POST /api/v1/bookings/{pnr}/payment-intents/{id}/confirm` — **sandbox only**, stands in for the
  provider's browser SDK
- `GET /api/v1/bookings/{pnr}/payments`
- `POST /api/v1/webhooks/payments/{provider}` — unauthenticated, signature-verified
- Tasks: `payments.handle_payment_succeeded` (webhook), `payments.reconcile_pending_payments`
  (beat, 5 min)

## Gotchas

- The sandbox reaches the booking **through the webhook**, not by mutating it inline, so dev and
  production exercise the same path. That is deliberate — do not "simplify" it.
- Ticketing is dispatched *after* the booking lock is released. `issue_tickets` takes the same
  lock, so dispatching inside it deadlocks under eager execution and is fragile in production.
- Adding a Celery task means **restarting the workers**. Autodiscovery runs at boot, and a task
  the worker has not seen fails with `Received unregistered task`, leaving the event unprocessed
  until reconciliation picks it up.
- 3-D Secure stops at `REQUIRES_ACTION`. The challenge flow is not implemented; the sandbox card
  `4000000000003220` exercises the branch.
- An intent is reused while it is live and the amount matches, so two tabs on the card form
  cannot become two charges.

## Testing

    make test-be app=payments

Required: a replayed webhook pays once; a forged signature is rejected; a decline leaves the hold
intact; the ledger nets to zero; a payment after hold expiry queues a refund and leaves the seats
released; the card number appears in no stored payload.
