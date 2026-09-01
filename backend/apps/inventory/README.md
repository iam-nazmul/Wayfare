# inventory

Schedules, dated flights, seat inventory, and the locking that stops overselling. The most
correctness-critical module in the backend.

## Responsibilities

- Owns: `Route`, `FlightSchedule`, `Flight`, `CabinConfig`, `BookingClass`, `Seat`,
  `SeatMapTemplate`, and every mutation of a seat count.
- Does not own: prices (`apps.pricing`), or who the seat is for (`apps.booking`). Inventory counts
  seats; it does not know a passenger's name.

## Key objects

| Object | Role |
|---|---|
| [models.py](models.py) `FlightSchedule` | Repeating pattern in **local** time |
| [models.py](models.py) `Flight` | One dated operation, unique on `(airline, flight_number, departure_utc)` |
| [models.py](models.py) `CabinConfig` | Physical capacity — **the hard ceiling** |
| [models.py](models.py) `BookingClass` | One RBD bucket; authorisations nest under the cabin |
| [services/availability.py](services/availability.py) | `cheapest_open_class`, `hold`, `release`, `confirm`, `unsell` |
| [services/materialise.py](services/materialise.py) | Schedule → dated flights + inventory + seats |
| [services/cache.py](services/cache.py) | Route-tagged search-cache invalidation |

## Invariants

- **The cabin is the ceiling; RBD authorisations are not.** `sum(BookingClass.authorised)` across a
  cabin deliberately exceeds `CabinConfig.capacity` — that is nested revenue-management inventory,
  not a bug. Overselling *authorisations* is normal. Overselling *seats* is prevented by the
  `cabin_not_oversold` check constraint and by `hold()` testing `cabin_config.seats_available`
  before the RBD.
- **All multi-segment locking goes through `_lock()`,** which sorts by `(flight_id, cabin, rbd)`.
  Any caller that locks inventory rows in a different order can deadlock against a concurrent
  booking. There is exactly one lock helper for this reason — do not hand-roll a second.
- **`hold` / `confirm` / `release` are not individually idempotent.** They move counters by a
  delta. Calling `release` twice for one hold under-counts and leaks seats. Idempotency belongs to
  the caller: the booking record and `InventoryHold.released_at` decide whether the call happens.
- **`cheapest_open_class` is lock-free on purpose.** Search must never block booking. Its answer is
  advisory and is always re-verified under `select_for_update` in `hold()`.
- **`build_inventory` sets every RBD's `authorised` to full cabin capacity.** Revenue management is
  expected to lower them. Leaving them wide open means the cheapest bucket sells the whole cabin.
- **Local time and UTC are both stored.** `materialise_schedule` converts the authored local time
  through the origin's zone per date, so a DST change moves `departure_utc` while
  `departure_local` — what the boarding pass prints — stays put.

## Entry points

- Public: `GET /api/v1/flights/{public_id}/seatmap?cabin=`
- Ops: `/api/v1/ops/schedules`, `/ops/routes`, `/ops/seat-maps`, `/ops/flights`,
  `POST /ops/schedules/{id}/materialise`, `GET|PATCH /ops/flights/{public_id}/inventory`,
  `GET /ops/flights/{public_id}/manifest`
- Tasks: `inventory.materialise_schedules` (beat, daily 02:00), `inventory.mark_departed_flights`
  (beat, 10 min), `inventory.recalculate_availability`
- CLI: `python manage.py seed_demo [--days 90]`

## Gotchas

- **Materialisation is idempotent through an `IntegrityError`.** A date that already exists trips
  `uniq_flight_departure` and is counted as skipped. That is the intended re-run path — do not
  "fix" it by pre-checking, which reintroduces a race.
- A schedule whose local times imply a non-positive duration (missing `arrival_day_offset` on an
  overnight flight) is **skipped with a warning**, not created. If a schedule silently produces no
  flights, check the day offset first.
- `mark_departed_flights` uses two bulk `update()` calls, so `save()` and signals do not fire and
  `updated_at` is set explicitly. Anything that needs to react to departure must be driven from the
  outbox, not a model signal.
- Editing capacity downward is refused below `seats_sold + seats_held` (409) — the check constraint
  would otherwise reject the write with a 500.
- `Seat` rows are created by `bulk_create(ignore_conflicts=True)`, so re-running seat generation is
  safe but will not update existing rows' fees or characteristics.

## Testing

    make test-be app=inventory

Required, and non-negotiable before any change here ships:

1. Eight concurrent `hold()` calls for the last seat: exactly one succeeds, seven raise
   `InventoryUnavailable`, and `seats_held` ends at 1. Must use `@pytest.mark.django_db(transaction=True)`.
2. `confirm()` moves a seat from held to sold without changing the total.
3. A schedule crossing a DST boundary keeps `departure_local` constant while `departure_utc` shifts.
4. An overnight schedule without `arrival_day_offset` is skipped, not created with a negative
   duration.
