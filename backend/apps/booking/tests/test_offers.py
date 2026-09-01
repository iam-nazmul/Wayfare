from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking.models import Offer, SearchQuery
from apps.booking.services.offers import build_offer, load_offer, sign, verify
from apps.common.exceptions import OfferExpired, OfferInvalid

pytestmark = pytest.mark.django_db


@pytest.fixture
def search_query(db):
    return SearchQuery.objects.create(
        origin="DAC", destination="DXB",
        depart_date=timezone.now().date() + timedelta(days=7),
        trip_type="ONE_WAY",
    )


@pytest.fixture
def offer(search_query):
    made = build_offer(
        search_query=search_query,
        itinerary={"origin": "DAC", "destination": "DXB", "stops": 0},
        price_breakdown={"total": {"amount": "500.00", "currency": "USD"}},
        total_amount="500.00",
        currency="USD",
        fare_family_id=None,
        seats_remaining=4,
    )
    made.save()
    return made


def test_signature_is_stable_for_the_same_payload():
    payload = {"itinerary": {"a": 1}, "price": {"b": 2}}
    assert sign(payload) == sign(dict(payload))


def test_signature_changes_with_the_payload():
    assert sign({"itinerary": {"a": 1}}) != sign({"itinerary": {"a": 2}})


def test_valid_offer_verifies(offer):
    assert verify(offer) is True


def test_load_offer_returns_a_valid_offer(offer):
    assert load_offer(offer.offer_id).pk == offer.pk


def test_tampered_price_is_rejected(offer):
    """The signature is what stops a client editing the price before booking."""
    offer.price_breakdown = {"total": {"amount": "1.00", "currency": "USD"}}
    offer.save(update_fields=["price_breakdown"])

    assert verify(offer) is False
    with pytest.raises(OfferInvalid):
        load_offer(offer.offer_id)


def test_tampered_itinerary_is_rejected(offer):
    offer.itinerary = {"origin": "DAC", "destination": "LHR", "stops": 0}
    offer.save(update_fields=["itinerary"])
    with pytest.raises(OfferInvalid):
        load_offer(offer.offer_id)


def test_expired_offer_is_rejected(offer):
    Offer.objects.filter(pk=offer.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(OfferExpired):
        load_offer(offer.offer_id)


def test_unknown_offer_is_rejected(db):
    import uuid

    with pytest.raises(OfferInvalid):
        load_offer(uuid.uuid4())


def test_offer_expiry_follows_the_configured_ttl(offer, settings):
    remaining = (offer.expires_at - timezone.now()).total_seconds()
    assert 0 < remaining <= settings.OFFER_TTL_MINUTES * 60 + 5
