import math
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings

from apps.inventory.models import Flight
from apps.inventory.selectors import connections_from, onward_flights, sellable_flights_on

#: Longest gap that still counts as a connection. Beyond 24h it is a stopover — a different trip.
MAX_CONNECT_HOURS = 12
#: Reject itineraries that wander: a leg may not move more than this fraction of the
#: great-circle distance away from the destination.
BACKTRACK_TOLERANCE = 0.25
#: Reject itineraries far slower than the fastest way to fly the market.
MAX_DURATION_MULTIPLIER = 3.0
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True, slots=True)
class Itinerary:
    flights: tuple[Flight, ...]

    @property
    def origin(self) -> str:
        return self.flights[0].origin_airport_id

    @property
    def destination(self) -> str:
        return self.flights[-1].destination_airport_id

    @property
    def stops(self) -> int:
        return len(self.flights) - 1

    @property
    def departure_utc(self):
        return self.flights[0].departure_utc

    @property
    def arrival_utc(self):
        return self.flights[-1].arrival_utc

    @property
    def total_minutes(self) -> int:
        return int((self.arrival_utc - self.departure_utc).total_seconds() // 60)

    @property
    def key(self) -> str:
        return "-".join(str(flight.id) for flight in self.flights)


def great_circle_km(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def minimum_connect_minutes(airport, arriving_country: str, departing_country: str) -> int:
    """Per-airport override wins; otherwise the global domestic/international default."""
    international = arriving_country != departing_country
    if international:
        return airport.mct_international_minutes or settings.MCT_INTERNATIONAL_MINUTES
    return airport.mct_domestic_minutes or settings.MCT_DOMESTIC_MINUTES


def build_itineraries(
    origin: str, destination: str, day: date, max_stops: int = 1, limit: int = 60
) -> list[Itinerary]:
    """Direct flights, then one- and two-stop connections that obey MCT and do not backtrack."""
    origin, destination = origin.upper(), destination.upper()

    directs = [Itinerary((flight,)) for flight in sellable_flights_on(origin, destination, day)]
    results = list(directs)

    if max_stops >= 1:
        results.extend(_with_connections(origin, destination, day, max_stops))

    if not results:
        return []

    fastest = min(itinerary.total_minutes for itinerary in results)
    ceiling = fastest * MAX_DURATION_MULTIPLIER

    filtered = [
        itinerary
        for itinerary in results
        if itinerary.total_minutes <= ceiling and not _backtracks(itinerary)
    ]

    filtered.sort(key=lambda i: (i.total_minutes, i.stops))
    return filtered[:limit]


def _with_connections(
    origin: str, destination: str, day: date, max_stops: int
) -> list[Itinerary]:
    results: list[Itinerary] = []

    for first in connections_from(origin, day):
        if first.destination_airport_id == destination:
            continue  # already covered as a direct

        window_start = first.arrival_utc + timedelta(
            minutes=minimum_connect_minutes(
                first.destination_airport,
                first.origin_airport.country_id,
                first.destination_airport.country_id,
            )
        )
        window_end = first.arrival_utc + timedelta(hours=MAX_CONNECT_HOURS)

        for second in onward_flights(first.destination_airport_id, window_start, window_end):
            if second.destination_airport_id == destination:
                results.append(Itinerary((first, second)))
            elif max_stops >= 2 and second.destination_airport_id != origin:
                third_start = second.arrival_utc + timedelta(
                    minutes=minimum_connect_minutes(
                        second.destination_airport,
                        second.origin_airport.country_id,
                        second.destination_airport.country_id,
                    )
                )
                third_end = second.arrival_utc + timedelta(hours=MAX_CONNECT_HOURS)
                for third in onward_flights(
                    second.destination_airport_id, third_start, third_end
                ):
                    if third.destination_airport_id == destination:
                        results.append(Itinerary((first, second, third)))

    return results


def _backtracks(itinerary: Itinerary) -> bool:
    """True when an intermediate stop is materially further from the destination than the origin."""
    if itinerary.stops == 0:
        return False

    final = itinerary.flights[-1].destination_airport
    start = itinerary.flights[0].origin_airport
    direct_km = great_circle_km(
        start.latitude, start.longitude, final.latitude, final.longitude
    )
    if direct_km == 0:
        return False

    for flight in itinerary.flights[:-1]:
        stop = flight.destination_airport
        remaining = great_circle_km(
            stop.latitude, stop.longitude, final.latitude, final.longitude
        )
        if remaining > direct_km * (1 + BACKTRACK_TOLERANCE):
            return True

    return False
