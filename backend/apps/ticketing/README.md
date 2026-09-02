# ticketing

E-tickets: allocating ticket numbers, writing one coupon per flown segment, and recording what
happens to them afterwards.

## Responsibilities

- Owns: `Ticket`, `TicketCoupon`, `TicketEvent`, `TicketSerial`, and ticket-number allocation.
- Owns the `PENDING_TICKETING → TICKETED` transition.
- Does not own: payment (`apps.payments`) or booking status rules
  (`booking/services/state.py::transition`).
- Not built yet: EMDs (there are no ancillaries to issue them against), void, exchange, refund of
  a coupon, and the itinerary PDF.

## Key objects

| Object | Role |
|---|---|
| [services/issue.py](services/issue.py) `issue_tickets` | One ticket per passenger, one coupon per segment |
| [services/numbers.py](services/numbers.py) `next_ticket_number` | Per-airline serial + IATA check digit |
| [services/numbers.py](services/numbers.py) `is_valid` | Check-digit validation for an inbound number |
| [tasks.py](tasks.py) `issue_tickets` | Dispatched after payment capture |
| [tasks.py](tasks.py) `void_expired_unticketed` | Alerts on money taken with no ticket behind it |

## Invariants

- **Only a paid booking is ticketed.** `issue_tickets` refuses anything but `PENDING_TICKETING`
  and raises `InvalidTransition`; a ticket is a financial document, not a UI state.
- **Issuing twice returns the same tickets.** The task is `acks_late` and will be redelivered, so
  a second run must not burn a second set of ticket numbers.
- **The ticket number is validated on write.** 13 digits: 3-digit airline prefix, 9-digit serial,
  check digit = the 12-digit body modulo 7.
- **Ticket totals sum to the booking total.** The remainder from dividing across passengers goes
  to the first, so the two never disagree by a cent.
- **A ticket's history is append-only.** `TicketEvent` rows are written, never edited.

## Entry points

- `GET /api/v1/bookings/{pnr}/tickets` — owner, staff, or guest with `?last_name=`. Returns `[]`
  rather than 404 while issuance is still running, because the client polls it.
- Tasks: `ticketing.issue_tickets` (after payment capture),
  `ticketing.void_expired_unticketed` (beat, 15 min)

## Gotchas

- **Serials come from a locked counter row, not a Postgres sequence.** SPEC.md §5.6 calls for a
  sequence per airline, but a sequence name cannot be a bound parameter, so that would mean
  interpolating DDL on every issue — against invariant 10. `TicketSerial` + `select_for_update`
  gives the same monotonic serial with no dynamic SQL. Numbers are contiguous rather than gapped,
  which a sequence would not guarantee anyway.
- `void_expired_unticketed` **voids nothing**. Money has changed hands by then, so it logs at
  ERROR for the ticketing desk instead of making that call itself.
- The unique constraint on `(booking, passenger)` is partial — it applies to `ISSUED` tickets
  only, so a reissue after a void is still possible.
- Coupon numbers start at 1, not 0. They are printed on the ticket and read aloud at the desk.

## Testing

    make test-be app=ticketing

Required: the check digit matches the body modulo 7; a corrupted number fails validation; serials
never repeat within an airline; issuing twice returns the same tickets; an unpaid booking cannot
be ticketed; ticket totals sum to the booking total.
