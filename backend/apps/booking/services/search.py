import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.analytics.events import push
from apps.inventory.constants import Cabin
from apps.inventory.services.availability import Availability, open_classes
from apps.inventory.services.cache import remember_search_key
from apps.pricing.constants import TripType
from apps.pricing.services.quote import (
    NoFareFound,
    PassengerCount,
    find_fare,
    quote_itinerary,
)

from ..models import Offer, SearchQuery
from .itineraries import Itinerary, build_itineraries
from .offers import build_offer

logger = logging.getLogger("wayfare.search")

CACHE_TTL_SECONDS = 60
#: Hard ceiling on a search. Past this the caller gets whatever priced so far, flagged partial.
BUDGET_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class SearchParams:
    origin: str
    destination: str
    depart_date: date
    return_date: date | None = None
    trip_type: str = TripType.ONE_WAY
    adults: int = 1
    children: int = 0
    infants: int = 0
    cabin: str = Cabin.ECONOMY
    currency: str = "USD"
    max_stops: int = 1

    @property
    def passengers(self) -> PassengerCount:
        return PassengerCount(self.adults, self.children, self.infants)

    def cache_key(self) -> str:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "o": self.origin, "d": self.destination,
                    "dep": str(self.depart_date), "ret": str(self.return_date),
                    "a": self.adults, "c": self.children, "i": self.infants,
                    "cab": self.cabin, "cur": self.currency, "stops": self.max_stops,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:32]
        return f"wf:search:{digest}"


def run_search(params: SearchParams, *, session_id: str = "", user=None) -> tuple[SearchQuery, list[Offer], bool]:
    """Price every viable itinerary for one slice.

    Returns ``(search_query, offers, partial)``. Read-only apart from the thin SearchQuery row
    and the Offer rows kept for audit — booking never depends on this path holding inventory.
    """
    started = time.perf_counter()
    key = params.cache_key()
    cached = cache.get(key)

    search_query = SearchQuery.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        session_id=session_id,
        origin=params.origin,
        destination=params.destination,
        depart_date=params.depart_date,
        return_date=params.return_date,
        trip_type=params.trip_type,
        pax_adults=params.adults,
        pax_children=params.children,
        pax_infants=params.infants,
        cabin=params.cabin,
        currency=params.currency,
        cache_hit=cached is not None,
    )

    if cached is not None:
        offers = _rehydrate(search_query, cached)
        _finish(search_query, offers, started, partial=False)
        return search_query, offers, False

    itineraries = build_itineraries(
        params.origin, params.destination, params.depart_date, max_stops=params.max_stops
    )

    offers: list[Offer] = []
    partial = False

    for itinerary in itineraries:
        if time.perf_counter() - started > BUDGET_SECONDS:
            partial = True
            logger.warning("search_budget_exceeded", extra={"key": key})
            break

        offer = _price(itinerary, params, search_query)
        if offer is not None:
            offers.append(offer)

    Offer.objects.bulk_create(offers)
    offers.sort(key=lambda o: o.total_amount)

    if not partial:
        cache.set(key, _dehydrate(offers), CACHE_TTL_SECONDS)
        remember_search_key(params.origin, params.destination, key)

    _finish(search_query, offers, started, partial=partial)
    return search_query, offers, partial


def _price(itinerary: Itinerary, params: SearchParams, search_query: SearchQuery) -> Offer | None:
    """Find the cheapest sellable class on every leg, then price the whole journey.

    A leg with no open class, or a journey with no qualifying fare, yields no offer — an
    itinerary that cannot be ticketed must never reach the customer.
    """
    legs = []
    seats_needed = params.passengers.seated
    seats_remaining = 999

    for flight in itinerary.flights:
        availability = _sellable_class(flight, params, seats_needed)
        if availability is None:
            return None
        legs.append((flight, params.cabin, availability.rbd))
        seats_remaining = min(seats_remaining, availability.seats_available)

    try:
        breakdown = quote_itinerary(
            legs,
            params.passengers,
            currency=params.currency,
            return_date=params.return_date,
        )
    except NoFareFound:
        return None

    return build_offer(
        search_query=search_query,
        itinerary=_itinerary_payload(itinerary, legs),
        price_breakdown=breakdown.as_dict(),
        total_amount=breakdown.total.amount,
        currency=breakdown.total.currency,
        fare_family_id=breakdown.segments[0].fare_family_id if breakdown.segments else None,
        seats_remaining=min(seats_remaining, 9),
    )


def _sellable_class(flight, params: SearchParams, seats_needed: int) -> Availability | None:
    """Cheapest open class on a leg whose fare the journey actually qualifies for.

    Seat availability and fare rules are separate gates. The cheapest bucket is often held back
    by an advance-purchase or stay rule, and an airline then sells the next one up rather than
    dropping the flight — so walk the ladder instead of giving up on the first miss.
    """
    departure = flight.departure_utc.date()

    for availability in open_classes(flight.id, params.cabin, seats_needed):
        fare = find_fare(
            flight,
            params.cabin,
            availability.rbd,
            departure=departure,
            return_date=params.return_date,
        )
        if fare is not None:
            return availability

    return None


def _itinerary_payload(itinerary: Itinerary, legs: list) -> dict:
    return {
        "origin": itinerary.origin,
        "destination": itinerary.destination,
        "stops": itinerary.stops,
        "duration_minutes": itinerary.total_minutes,
        "departure_utc": itinerary.departure_utc.isoformat(),
        "arrival_utc": itinerary.arrival_utc.isoformat(),
        "segments": [
            {
                "flight_id": flight.id,
                "flight_public_id": str(flight.public_id),
                "designator": flight.designator,
                "airline": flight.airline_id,
                "origin": flight.origin_airport_id,
                "destination": flight.destination_airport_id,
                "departure_utc": flight.departure_utc.isoformat(),
                "arrival_utc": flight.arrival_utc.isoformat(),
                "departure_local": flight.departure_local.isoformat(),
                "arrival_local": flight.arrival_local.isoformat(),
                "duration_minutes": flight.duration_minutes,
                "aircraft": flight.aircraft_id,
                "cabin": cabin,
                "rbd": rbd,
            }
            for (flight, cabin, rbd) in legs
        ],
    }


def _dehydrate(offers: list[Offer]) -> list[dict]:
    return [
        {
            "itinerary": offer.itinerary,
            "price_breakdown": offer.price_breakdown,
            "total_amount": str(offer.total_amount),
            "currency": offer.currency,
            "fare_family_id": offer.fare_family_id,
            "seats_remaining": offer.seats_remaining,
        }
        for offer in offers
    ]


def _rehydrate(search_query: SearchQuery, cached: list[dict]) -> list[Offer]:
    """Re-issue offers from a cache hit.

    Each cache hit mints fresh offer ids and expiries: the price is 60 seconds old at worst, but
    the booking window should start now, not when the first searcher looked.
    """
    offers = [
        build_offer(
            search_query=search_query,
            itinerary=entry["itinerary"],
            price_breakdown=entry["price_breakdown"],
            total_amount=entry["total_amount"],
            currency=entry["currency"],
            fare_family_id=entry["fare_family_id"],
            seats_remaining=entry["seats_remaining"],
        )
        for entry in cached
    ]
    Offer.objects.bulk_create(offers)
    return offers


def _finish(search_query: SearchQuery, offers: list[Offer], started: float, partial: bool) -> None:
    latency_ms = int((time.perf_counter() - started) * 1000)
    amounts = sorted(offer.total_amount for offer in offers)

    SearchQuery.objects.filter(pk=search_query.pk).update(
        results_count=len(offers), latency_ms=latency_ms
    )
    search_query.results_count = len(offers)
    search_query.latency_ms = latency_ms

    push(
        "search",
        {
            "search_id": str(search_query.public_id),
            "event_time": timezone.now().isoformat(),
            "session_id": search_query.session_id,
            "user_id": search_query.user_id,
            "origin": search_query.origin,
            "destination": search_query.destination,
            "depart_date": str(search_query.depart_date),
            "return_date": str(search_query.return_date) if search_query.return_date else None,
            "trip_type": search_query.trip_type,
            "pax_adults": search_query.pax_adults,
            "pax_children": search_query.pax_children,
            "pax_infants": search_query.pax_infants,
            "cabin": search_query.cabin,
            "currency": search_query.currency,
            "results_count": len(offers),
            "cheapest_amount": str(amounts[0]) if amounts else "0",
            "median_amount": str(amounts[len(amounts) // 2]) if amounts else "0",
            "cache_hit": int(search_query.cache_hit),
            "latency_ms": latency_ms,
            "partial": int(partial),
        },
    )
