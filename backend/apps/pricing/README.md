# pricing

Fares, fare families, taxes, fees, promotions, and the quote engine that turns an itinerary into a
price.

## Responsibilities

- Owns: `FareFamily`, `Fare`, `TaxRule`, `FeeRule`, `PromoCode`, and every calculation that
  produces money.
- Does not own: seat counts (`apps.inventory`) or what was actually charged (`apps.payments`). A
  quote is an opinion; the ledger is the fact.

## Key objects

| Object | Role |
|---|---|
| [models.py](models.py) `FareFamily` | Changeability, refundability, baggage — the rules a refund later reads |
| [models.py](models.py) `Fare` | Published fare per market, cabin and RBD |
| [models.py](models.py) `TaxRule` | Scoped per departure / arrival / segment / itinerary |
| [services/quote.py](services/quote.py) `quote_itinerary` | The entry point. Returns a `PriceBreakdown` |
| [services/quote.py](services/quote.py) `find_fare` | Applies AP and min/max stay gates |
| [services/quote.py](services/quote.py) `passenger_type_for` | Age at the **return** date |
| [constants.py](constants.py) `DEFAULT_PAX_DISCOUNT` | Child 75%, infant 10% when no typed fare exists |

## Invariants

- **Every amount is a `Money`.** `quote_itinerary` builds `Money` objects throughout and never
  returns a bare `Decimal`. Mixing currencies raises `CurrencyMismatch` rather than silently
  summing.
- **Advance purchase and min/max stay are gates, not preferences.** `find_fare` filters them out
  because a fare the traveller does not qualify for cannot be issued at ticketing — offering it
  produces a booking that fails days later.
- **Passenger type is evaluated at the return date.** A child who turns 12 mid-trip is an adult for
  the whole journey. Using the outbound date instead is the classic bug that gets a passenger
  refused boarding on the way home.
- **`NoFareFound` must propagate.** Search catches it and drops the itinerary. Never substitute a
  default price — an unpriceable itinerary must not reach a customer.
- **Taxes are not uniformly refundable.** `TaxRule.is_refundable` drives the refund calculation in
  M5; a "full refund" of a refundable fare still withholds non-refundable taxes.
- **A typed fare beats a discounted adult fare.** `find_fare` prefers a fare published for the exact
  passenger type and only falls back to `DEFAULT_PAX_DISCOUNT`.

## Entry points

- Called by `apps.booking.services.search` for every candidate itinerary.
- Tasks: `pricing.refresh_exchange_rates` (beat, daily 03:00),
  `pricing.rebuild_calendar_cache` (beat, daily 04:00)

## Gotchas

- `_taxes` multiplies by `passengers.total`, which **includes infants**. Infants take no seat but do
  pay most taxes — that is correct, and differs from the seat-inventory count
  (`passengers.seated`).
- `TaxRule` with both `country` and `airport` null applies to every itinerary. The unique constraint
  is on `(code, country, airport)`, so one code can exist globally and be overridden per country.
- `rebuild_calendar_cache` needs a cache backend with `delete_pattern` (django-redis). On the
  built-in Redis backend it logs and returns 0 rather than failing — the calendar then ages out on
  its own 15-minute TTL.
- Fare seeding builds a ladder where each step down the RBD list adds 18%, so the cheapest open
  bucket really is the cheapest fare. Change the ladder and search results stop being meaningful.

## Testing

    make test-be app=pricing

Required: the AP boundary (a fare with `advance_purchase_days=3` is unavailable 2 days out and
available at 3); min/max stay boundaries; a child priced from a typed fare vs. a discounted adult
fare; tax multipliers for each scope.
