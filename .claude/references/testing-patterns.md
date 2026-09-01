# Testing patterns

Authority: [SPEC.md](../../SPEC.md) §14.

## Layout

```
apps/<app>/tests/
├── factories.py       # factory_boy, one factory per model
├── test_services.py   # domain logic, the bulk of the coverage
├── test_selectors.py  # ownership filtering, query counts
└── test_api.py        # happy / auth-denied / validation / conflict per endpoint
```

Bar: ≥ 90% on `services/`, `pricing/`, `ticketing/`. Coverage elsewhere follows from the API tests.

## Every endpoint gets four tests

```python
def test_create_booking_succeeds(...)          # happy path, asserts state + response shape
def test_create_booking_requires_auth(...)     # 401/403
def test_create_booking_validates_pax(...)     # 422 with field errors
def test_create_booking_conflicts_when_sold_out(...)   # 409 problem detail
```

## Factories

```python
class FlightFactory(DjangoModelFactory):
    class Meta:
        model = Flight
    airline = SubFactory(AirlineFactory)
    departure_utc = LazyFunction(lambda: timezone.now() + timedelta(days=30))

    @post_generation
    def cabins(obj, create, extracted, **kwargs):
        if create:
            CabinConfigFactory(flight=obj, cabin=Cabin.ECONOMY, capacity=180)
```

Factories build valid objects by default. A test that needs an invalid state constructs it
explicitly, so the invalidity is visible in the test.

## The concurrency test (required for any inventory change)

```python
@pytest.mark.django_db(transaction=True)
def test_last_seat_is_sold_once():
    flight = FlightFactory(cabins__capacity=1)
    offer = make_offer(flight, seats=1)
    results = run_in_threads(lambda: try_book(offer), n=8)
    assert sum(r.ok for r in results) == 1
    assert all(r.code == "inventory_unavailable" for r in results if not r.ok)
    flight.refresh_from_db()
    assert flight.economy.seats_sold == 1
```

`transaction=True` is mandatory — the default wrapping transaction hides lock behaviour.

## The idempotency test (required for any money path)

Call twice with the same `Idempotency-Key`, or deliver the same webhook twice. Assert: one
`Payment`, one ticket set, one ledger pair, identical response body.

## Time

`freezegun` for hold expiry, check-in windows, refund penalty ladders, advance-purchase rules.
Never `sleep`. Test the boundaries of every ladder, not the middle.

## Query counts

```python
with assertNumQueries(6):
    client.get("/api/v1/me/bookings")
```

On every list endpoint. Catches N+1 before it reaches load testing.

## What not to test

Django's ORM, DRF's serializers, the provider SDK. Mock the payment provider at the
`PaymentProvider` protocol boundary — use `SandboxProvider`, whose outcomes are deterministic by
card number (`4242…` succeeds, `4000…0002` declines, `4000…3220` needs 3DS).

## ClickHouse tests

Run against the compose instance. Assert that DDL applies cleanly, that a materialised view's
output matches the same aggregation computed over raw rows, and that ingestion dedups on
`event_id`.

## Frontend

Vitest + Testing Library. Test behaviour through the DOM, not implementation:
query by role and label, never by class name. MSW mocks the API using the **generated** types, so a
contract change breaks the tests rather than silently passing.

## E2E (Playwright)

Five flows are always green before merge: search→book→pay→ticket, change/exchange, cancel+refund,
check-in→boarding pass, ops refund approval. They run against the compose stack with `make seed`
data.
