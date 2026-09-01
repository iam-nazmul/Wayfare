# Django app layout

Every app under `backend/apps/` has the same shape. Deviating makes the codebase unnavigable for
agents.

```
apps/<app>/
├── README.md              # for developers/agents — responsibilities, models, invariants, testing
├── __init__.py
├── apps.py
├── models.py              # or models/ package when > ~400 lines
├── serializers.py
├── views.py
├── urls.py
├── selectors.py           # ALL reads. Ownership filtering lives here.
├── services/              # ALL writes and domain logic
│   ├── __init__.py
│   └── <verb>.py          # create_booking.py, quote_change.py, issue_tickets.py
├── tasks.py
├── admin.py
├── constants.py           # enums, status choices, codes
├── migrations/
└── tests/
    ├── factories.py
    ├── test_services.py
    ├── test_api.py
    └── test_selectors.py
```

## Layer responsibilities

| Layer | Does | Never does |
|---|---|---|
| `views.py` | Parse, validate, delegate to a service, serialize the result | Business rules, ORM writes, cross-model orchestration |
| `serializers.py` | Shape and field-validate | Query the DB for authorisation, mutate |
| `services/` | Domain logic, transactions, locks, state transitions, outbox writes | HTTP concerns, `request` objects |
| `selectors.py` | Every read, pre-filtered by actor | Writes |
| `models.py` | Field definitions, constraints, tiny derived properties | Business orchestration in `save()`, signals with side effects |
| `tasks.py` | Thin Celery wrappers that call services | Domain logic inline |

## Service function shape

```python
def create_booking(*, offer_id: str, passengers: list[PassengerData],
                   contact: ContactData, actor: User | None) -> Booking:
    offer = load_and_verify_offer(offer_id)
    with transaction.atomic():
        _lock_and_reserve_inventory(offer)
        booking = _create_booking_rows(offer, passengers, contact, actor)
        OutboxEvent.objects.create(
            aggregate_type="booking", aggregate_id=booking.id,
            event_type="booking_held", payload=serialize_booking_event(booking),
        )
    return booking
```

Rules:
- Keyword-only arguments. Explicit `actor`, never `request.user` reached from inside.
- Return domain objects, not serialized dicts.
- Raise domain exceptions (`InventoryUnavailable`, `OfferExpired`, `InvalidTransition`) from
  `apps.common.exceptions`; the DRF handler maps them to problem details.
- One `transaction.atomic()` per service entry point. Never open a transaction in a view.
- No I/O to external services inside the transaction — write an `OutboxEvent` instead.

## Selector shape

```python
def bookings_for(actor: User) -> QuerySet[Booking]:
    qs = Booking.objects.select_related("user", "agency").prefetch_related("segments__flight")
    if actor.is_staff:
        return qs
    if agency_id := actor.agency_id:
        return qs.filter(agency_id=agency_id)
    return qs.filter(user=actor)
```

Always `select_related` / `prefetch_related` for what the serializer touches. N+1 in a list
endpoint is a review blocker; `test_api.py` asserts query counts with `assertNumQueries`.

## Models

- Inherit `apps.common.models.TimestampedModel` (`created_at`, `updated_at`) and
  `PublicIdModel` (UUIDv7 `public_id`) where the object is API-addressable.
- Express invariants as DB constraints, not just Python:
  `CheckConstraint(condition=Q(seats_sold__lte=F("capacity") + F("oversell_allowance")))`.
- Status fields use `TextChoices` in `constants.py`, never bare strings.
- Index what you filter on. Partial indexes for hot subsets
  (`WHERE processed_at IS NULL`, `WHERE status IN ('SCHEDULED','DELAYED')`).

## Adding an app

1. `python manage.py startapp <name> apps/<name>`, then reshape to the layout above.
2. Add to `INSTALLED_APPS`, mount `urls.py` under `/api/v1/`.
3. Write `README.md` (see the `module-readme` skill) — same commit, not later.
4. Factories in `tests/factories.py` before the first test.
