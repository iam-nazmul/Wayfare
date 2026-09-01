# catalog

Reference data: the world the airline flies in. Slow-changing, heavily cached, read by everything.

## Responsibilities

- Owns: countries, cities, airports, airlines, aircraft types, currencies, FX rates.
- Does not own: routes, schedules, or flights — those are `apps.inventory`. A `Route` is a
  commercial decision; an `Airport` is a fact about the world.

## Key objects

| Object | Role |
|---|---|
| [models.py](models.py) `Airport` | **PK is `iata_code`.** Carries the IANA timezone schedules are authored in |
| [models.py](models.py) `Airline` | **PK is `iata_code`.** `ticketing_prefix` is the first 3 digits of every e-ticket |
| [models.py](models.py) `Aircraft` | Type code, used to pick a seat-map template |
| [models.py](models.py) `ExchangeRate` | Dated rates; `latest_rate` reads the newest on or before today |
| [selectors.py](selectors.py) `search_airports` | Typeahead: exact IATA first, then trigram rank |

## Invariants

- **`Airport` and `Airline` use natural primary keys.** `flight.origin_airport_id` *is* `"DAC"` and
  `flight.airline_id` *is* `"WF"`. Code across inventory, search, and serialization relies on this;
  switching either to a surrogate key silently breaks `Flight.designator` and every route filter.
- **`Airport.timezone` is the authoring timezone for schedules.** Changing it after flights are
  materialised does not move existing flights — their UTC times are already fixed. Re-materialise
  if a timezone is corrected.
- **Trigram search needs the `pg_trgm` extension**, created by `catalog.0001_initial` via
  `TrigramExtension()`. On a database where the app user is not a superuser, that migration fails
  and the extension must be created out of band.
- **FX rates are dated, never overwritten.** Insert a new row with a new `valid_from`; the unique
  constraint is on `(base, quote, valid_from)`.

## Entry points

- `GET /api/v1/airports?q=&country=` — typeahead, `AllowAny`, unpaginated, capped at 15
- `GET /api/v1/airlines` · `/aircraft` · `/currencies` — `AllowAny`, unpaginated

All four are public: the search box is the first thing an anonymous visitor touches.

## Gotchas

- `search_airports` short-circuits to an exact match for 1–3 alphabetic characters. Typing "LON"
  returns nothing by exact match and falls through to trigram, which finds London's airports by
  city name — that fallthrough is the reason the exact branch checks `.exists()` first.
- The trigram threshold is 0.15, deliberately loose, because it is OR'd with prefix and
  `icontains` matches. Tightening it without checking those branches will not reduce noise.
- Airports are seeded with no `mct_*` overrides, so the global 45/90-minute MCT applies. Set the
  override per airport for hubs with long inter-terminal transfers.

## Testing

    make test-be app=catalog

Required: exact IATA beats a fuzzy name match; an inactive airport never appears; `latest_rate`
picks the newest rate not in the future.
