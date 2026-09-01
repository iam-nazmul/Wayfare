from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from . import selectors
from .models import Aircraft
from .serializers import (
    AircraftSerializer,
    AirlineSerializer,
    AirportSerializer,
    CurrencySerializer,
)


@extend_schema(
    tags=["catalog"],
    parameters=[
        OpenApiParameter("q", str, description="Free text: IATA code, airport or city name"),
        OpenApiParameter("country", str, description="ISO-3166 alpha-2 filter"),
    ],
)
class AirportListView(ListAPIView):
    """Airport typeahead. Public: the search box is the first thing an anonymous visitor uses."""

    serializer_class = AirportSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return selectors.search_airports(
            self.request.query_params.get("q", ""),
            self.request.query_params.get("country", ""),
        )


@extend_schema(tags=["catalog"])
class AirlineListView(ListAPIView):
    serializer_class = AirlineSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return selectors.active_airlines()


@extend_schema(tags=["catalog"])
class AircraftListView(ListAPIView):
    serializer_class = AircraftSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    queryset = Aircraft.objects.all()


@extend_schema(tags=["catalog"])
class CurrencyListView(ListAPIView):
    serializer_class = CurrencySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return selectors.currencies()
