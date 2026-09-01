import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.common.exceptions import OfferExpired, OfferInvalid

from ..models import Offer


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign(payload: dict) -> str:
    """HMAC over the priced payload.

    Search is stateless and cacheable, so the offer travels through the client. The signature is
    what stops the client editing the price before booking it.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(), _canonical(payload), hashlib.sha256
    ).hexdigest()


def verify(offer: Offer) -> bool:
    expected = sign({"itinerary": offer.itinerary, "price": offer.price_breakdown})
    return hmac.compare_digest(expected, offer.signature)


def build_offer(
    *,
    search_query,
    itinerary: dict,
    price_breakdown: dict,
    total_amount,
    currency: str,
    fare_family_id: int | None,
    seats_remaining: int,
) -> Offer:
    payload = {"itinerary": itinerary, "price": price_breakdown}
    return Offer(
        search_query=search_query,
        itinerary=itinerary,
        price_breakdown=price_breakdown,
        total_amount=total_amount,
        currency=currency,
        fare_family_id=fare_family_id,
        seats_remaining=seats_remaining,
        expires_at=timezone.now() + timedelta(minutes=settings.OFFER_TTL_MINUTES),
        signature=sign(payload),
    )


def load_offer(offer_id) -> Offer:
    """Fetch and validate an offer for booking.

    Checks identity, tamper-evidence and expiry. It does **not** check availability — that is
    re-read under lock in the booking transaction, because seats can go between the two.
    """
    offer = Offer.objects.filter(offer_id=offer_id).select_related("fare_family").first()
    if offer is None:
        raise OfferInvalid("That offer does not exist.")

    if not verify(offer):
        raise OfferInvalid("This offer has been altered and cannot be booked.")

    if offer.expires_at <= timezone.now():
        raise OfferExpired("Prices have moved on. Search again to get a current fare.")

    return offer
