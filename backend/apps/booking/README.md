# booking

Search, offers, and (from M3) PNRs. Currently the read-only half: building itineraries, pricing
them, and issuing signed offers.

## Responsibilities

- Owns: `SearchQuery`, `Offer`, itinerary construction, and the search orchestration.
- Will own (M3): `Booking`, `BookingSegment`, `Passenger`, `SeatAssignment`, `InventoryHold`.
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

## Entry points

- `POST /api/v1/search/flights` — one slice per journey leg; returns a `search_id` per slice
- `GET /api/v1/search/flights/{search_id}/offers?sort=&max_stops=&airline=`
- `GET /api/v1/offers/{offer_id}` — re-validate before booking
- `GET /api/v1/search/calendar?origin=&destination=&month=`
- Tasks: `booking.expire_offers` (beat, 5 min), `booking.release_expired_holds` (M3)

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

## Testing

    make test-be app=booking

Required: a tampered offer fails `verify`; an expired offer raises `OfferExpired`; a connection
under MCT is excluded; a backtracking itinerary is excluded; a round trip prices both slices with
the same return date.
