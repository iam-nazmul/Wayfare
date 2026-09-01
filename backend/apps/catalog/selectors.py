from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, QuerySet, Value
from django.db.models.functions import Greatest

from .models import Airline, Airport, Currency, ExchangeRate

TYPEAHEAD_LIMIT = 15


def active_airports() -> QuerySet[Airport]:
    return Airport.objects.filter(is_active=True).select_related("city", "country")


def search_airports(query: str, country: str = "") -> QuerySet[Airport]:
    """Typeahead over code, airport name and city name.

    An exact IATA code always ranks first — a traveller typing "DAC" means that airport, not
    every airport whose name happens to contain those letters.
    """
    qs = active_airports()
    if country:
        qs = qs.filter(country_id=country.upper())

    query = query.strip()
    if not query:
        return qs.order_by("iata_code")[:TYPEAHEAD_LIMIT]

    if len(query) <= 3 and query.isalpha():
        exact = qs.filter(iata_code__iexact=query)
        if exact.exists():
            return exact

    return (
        qs.annotate(
            rank=Greatest(
                TrigramSimilarity("iata_code", query),
                TrigramSimilarity("name", query),
                TrigramSimilarity("city__name", query),
                Value(0.0),
            )
        )
        .filter(
            Q(rank__gt=0.15)
            | Q(iata_code__istartswith=query)
            | Q(name__icontains=query)
            | Q(city__name__icontains=query)
        )
        .order_by("-rank", "iata_code")[:TYPEAHEAD_LIMIT]
    )


def active_airlines() -> QuerySet[Airline]:
    return Airline.objects.filter(is_active=True).select_related("country")


def currencies() -> QuerySet[Currency]:
    return Currency.objects.all()


def latest_rate(base: str, quote: str) -> ExchangeRate | None:
    return (
        ExchangeRate.objects.filter(base=base.upper(), quote=quote.upper())
        .order_by("-valid_from")
        .first()
    )
