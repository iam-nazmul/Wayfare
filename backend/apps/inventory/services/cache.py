import logging

from django.core.cache import cache

from ..models import Flight

logger = logging.getLogger("wayfare.inventory")

ROUTE_INDEX = "wf:idx:route:{origin}:{destination}"


def route_index_key(origin: str, destination: str) -> str:
    return ROUTE_INDEX.format(origin=origin, destination=destination)


def remember_search_key(origin: str, destination: str, search_key: str) -> None:
    """Tag a cached search result so an inventory write can sweep it immediately."""
    index = route_index_key(origin, destination)
    keys = cache.get(index) or set()
    keys.add(search_key)
    cache.set(index, keys, timeout=3600)


def invalidate_route(origin: str, destination: str) -> int:
    index = route_index_key(origin, destination)
    keys = cache.get(index) or set()
    if keys:
        cache.delete_many(list(keys))
    cache.delete(index)
    return len(keys)


def invalidate_flight(flight_id: int) -> int:
    """Sweep both directions — a return search caches under the reverse pair."""
    flight = (
        Flight.objects.filter(id=flight_id)
        .values_list("origin_airport_id", "destination_airport_id")
        .first()
    )
    if not flight:
        return 0

    origin, destination = flight
    swept = invalidate_route(origin, destination) + invalidate_route(destination, origin)
    logger.info("search_cache_swept", extra={"flight_id": flight_id, "keys": swept})
    return swept
