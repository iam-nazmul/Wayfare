# booking

Search, offers, and PNRs: building itineraries, pricing them, issuing signed offers, and
turning an accepted offer into a booking that holds real seats.

## Responsibilities

- Owns: `SearchQuery`, `Offer`, `Booking`, `BookingSegment`, `Passenger`, `InventoryHold`,
  itinerary construction, the search orchestration, the booking state machine, and the
  cancel / void / exchange servicing flows.
- Will own (later): `SeatAssignment`, `SpecialServiceRequest`, `BookingAncillary`.
- Does not own: seat counts (`apps.inventory`) or prices (`apps.pricing`). This module composes
  them.

## Key objects

| Object | Role |
|---|---|
| [services/search.py](services/search.py) `run_search` | Orchestrates: cache → itineraries → availability → quote → offers |
| [services/itineraries.py](services/itineraries.py) `build_itineraries` | Directs plus connections, MCT-aware |
| [services/offers.py](services/offers.py) `sign` / `verify` | HMAC tamper-evidence over the priced payload |
| [services/offers.py](services/offers.py) `load_offer` | Identity + signature + expiry check for booking |
| [models.py](models.py) `Offer` | Priced result. **Holds no inventory** |
| [services/booking.py](services/booking.py) `create_booking` | Offer → locked hold → PNR, in one transaction |
| [services/state.py](services/state.py) `transition` | The only way `Booking.status` changes |
| [services/pnr.py](services/pnr.py) `create_with_pnr` | PNR minting, retried on collision |
| [services/pax.py](services/pax.py) `pax_type_for` | Passenger type derived from DOB at the return date |
| [selectors.py](selectors.py) `bookings_for` / `guest_booking` | Every ownership check lives here |
| [services/cancel.py](services/cancel.py) `cancel_booking` | Release seats, quote the refund, raise it |
| [services/cancel.py](services/cancel.py) `is_voidable` | The same-day void window |
| [services/change.py](services/change.py) `quote_change` / `confirm_change` | Price and stage an exchange |
| [services/change.py](services/change.py) `abandon_change` | Roll back an exchange nobody paid for |

## Invariants

- **An offer is not a reservation.** It holds nothing. `load_offer` deliberately does *not* check
  availability — that is re-read under `select_for_update` inside the booking transaction, because
  seats can go between the two calls. Anything that treats an unexpired offer as a guaranteed seat
  is wrong.
- **Offers are signed.** Search is stateless and cacheable, so the priced payload travels through
  the client. `verify()` uses `hmac.compare_digest`; without it a client could edit the price.
- **Search never holds a lock and never mutates inventory.** `cheapest_open_class` is lock-free so
  a burst of searches cannot block the booking path.
- **An itinerary that cannot be priced yields no offer.** `_price` returns `None` on a closed class
  or `NoFareFound`, so unbookable results never surface.
- **Cache hits mint fresh offer ids and expiries.** A 60-second-old price is fine; a 60-second-old
  *booking window* is not, so `_rehydrate` re-issues rather than replaying stored offers.
- **Booking re-reads availability under lock.** `create_booking` calls `availability.hold`, which
  takes `SELECT … FOR UPDATE` on `CabinConfig` and `BookingClass`. The offer's signature and expiry
  are checked first, but neither says anything about whether the seats are still there.
- **Status never moves by assignment.** `transition()` owns the frozen machine in
  `services/state.py`, bumps `version`, and writes the audit row. It is guarded on the status it
  read, so a concurrent mover loses rather than overwrites.
- **Infants consume no seat inventory.** `seats_needed` counts ADT + CHD only; each infant is
  attached to its own adult via `associated_adult`.
- **`booking_held` goes to the outbox, not to an email.** Nothing leaves the process inside the
  booking transaction.
- **Cancelling releases the seats before anyone approves the money.** Whether a refund is owed is
  a fare-rule question that can wait for a human; a seat held by a cancelled booking is one
  nobody can sell.
- **An exchange keeps the old seats until the delta is paid.** New inventory is held first, the
  old stays sold, and the swap happens at reissue. A traveller who abandons a change still holds
  the ticket they started with — `abandon_change` is what puts it back.

## Entry points

- `POST /api/v1/search/flights` — one slice per journey leg; returns a `search_id` per slice
- `GET /api/v1/search/flights/{search_id}/offers?sort=&max_stops=&airline=`
- `GET /api/v1/offers/{offer_id}` — re-validate before booking
- `GET /api/v1/search/calendar?origin=&destination=&month=`
- `POST /api/v1/bookings` — offer → held PNR. `Idempotency-Key` required, `booking_create` throttle
- `GET /api/v1/bookings/{pnr}` — owner or staff via the selector, guests with `?last_name=`
- `POST /api/v1/bookings/{pnr}/cancel` — `quote_only` prices it without cancelling
- `POST /api/v1/bookings/{pnr}/change/quote` · `/change/confirm` — exchange flow
- Tasks: `booking.expire_offers` (beat, 5 min), `booking.release_expired_holds` (beat, 60 s)

## Gotchas

- **The outbound slice is priced with the return date.** Min/max stay rules apply to the journey,
  not the leg, so `SearchParams.return_date` is set on *both* slices of a round trip. Dropping it
  makes restricted fares wrongly available.
- Connection search runs a query per candidate first leg. It is bounded by the
  `MAX_CONNECT_HOURS = 12` window and the 3-second budget, after which results come back flagged
  `partial: true`. If searches go partial routinely, add the index before widening the budget.
- `_backtracks` needs airport latitude and longitude. Airports seeded without coordinates return a
  0 km great-circle distance and the check silently passes everything.
- The fare calendar reads offers produced by *real* searches, so a month nobody has searched shows
  empty days. It is a browsing aid, not a quotable price.
- `Offer` rows accumulate fast — one per priced itinerary per search. `booking.expire_offers` is
  what keeps the table and the calendar aggregate usable.
- **A wrong surname on guest retrieval is a 404, never a 403.** A 403 would confirm the PNR exists.
- Passenger type is judged at the *return* date, so a child who turns 12 mid-journey books as an
  adult. `_reference_date` in [views.py](views.py) picks that date; one-way falls back to arrival.
- `release_expired_holds` takes a Redis lock per PNR *and* re-reads status inside the transaction.
  The lock only reduces contention — a payment landing at the same moment is why the re-read
  exists. It sweeps `CHANGE_PENDING` as well as `HELD`: an unpaid exchange is abandoned rather
  than expired, because the passenger has already paid for the original journey.
- **A same-day cancellation is a void, not a refund** — full amount, no penalty, coupons
  untouched. Once the ticket is a day old the penalty ladder applies instead, so a test that
  cancels immediately is exercising the void path whether it meant to or not.
- The fare family that sets the change fee is the one being changed *out of*, read from the
  segment still `CONFIRMED` — not the new offer's family.

## Testing

    make test-be app=booking

Required: a tampered offer fails `verify`; an expired offer raises `OfferExpired`; a connection
under MCT is excluded; a backtracking itinerary is excluded; a round trip prices both slices with
the same return date; booking twice with one `Idempotency-Key` yields one PNR; seats sold between
search and booking give 409 `inventory_unavailable`; an expired hold releases its seats exactly
once; a same-day cancel is a penalty-free void; an exchange links the new ticket to the old
through `conjunction_of` and leaves the ledger at zero.
