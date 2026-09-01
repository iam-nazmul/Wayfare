from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Min
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pricing.constants import TripType

from .models import Offer, SearchQuery
from .serializers import (
    CalendarEntrySerializer,
    OfferSerializer,
    SearchRequestSerializer,
    SearchResponseSerializer,
)
from .services.offers import load_offer
from .services.search import SearchParams, run_search

CALENDAR_CACHE_SECONDS = 900


class SearchThrottleMixin:
    """Anonymous search is cheap but abusable; authenticated users get the higher bucket."""

    def get_throttles(self):
        self.throttle_scope = (
            "search_authenticated"
            if self.request.user and self.request.user.is_authenticated
            else "search"
        )
        return super().get_throttles()


@extend_schema(tags=["search"])
class FlightSearchView(SearchThrottleMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SearchRequestSerializer,
        responses={200: SearchResponseSerializer},
        description=(
            "Price every viable itinerary for each slice. Offers are signed and expire; they "
            "hold no inventory, which is re-checked when the booking is created."
        ),
    )
    def post(self, request):
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        passengers = data["passengers"]
        slices = data["slices"]
        return_date = slices[1]["date"] if data["trip_type"] == TripType.ROUND_TRIP else None

        results = []
        partial_any = False

        for index, slice_data in enumerate(slices):
            params = SearchParams(
                origin=slice_data["origin"].upper(),
                destination=slice_data["destination"].upper(),
                depart_date=slice_data["date"],
                # Min/max stay rules are evaluated against the whole journey, so the outbound
                # slice must know when the traveller comes back.
                return_date=return_date,
                trip_type=data["trip_type"],
                adults=passengers["adults"],
                children=passengers["children"],
                infants=passengers["infants"],
                cabin=data["cabin"],
                currency=data["currency"].upper(),
                max_stops=data["max_stops"],
            )
            search_query, offers, partial = run_search(
                params,
                session_id=request.headers.get("X-Session-Id", ""),
                user=request.user,
            )
            partial_any = partial_any or partial
            results.append(
                {
                    "index": index,
                    "search_id": search_query.public_id,
                    "origin": params.origin,
                    "destination": params.destination,
                    "date": params.depart_date,
                    "offers": OfferSerializer(offers, many=True).data,
                }
            )

        return Response(
            {
                "trip_type": data["trip_type"],
                "currency": data["currency"].upper(),
                "partial": partial_any,
                "slices": results,
            }
        )


@extend_schema(
    tags=["search"],
    parameters=[
        OpenApiParameter("sort", str, description="price | duration | departure"),
        OpenApiParameter("max_stops", int),
        OpenApiParameter("airline", str, description="Filter by marketing airline IATA code"),
    ],
)
class SearchOffersView(SearchThrottleMixin, ListAPIView):
    """Paginated, filterable view of one search's offers."""

    serializer_class = OfferSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        search = SearchQuery.objects.get(public_id=self.kwargs["search_id"])
        queryset = Offer.objects.filter(search_query=search)

        params = self.request.query_params
        if (max_stops := params.get("max_stops")) is not None:
            queryset = queryset.filter(itinerary__stops__lte=int(max_stops))
        if airline := params.get("airline"):
            queryset = queryset.filter(itinerary__segments__0__airline=airline.upper())

        sort = params.get("sort", "price")
        ordering = {
            "price": ("total_amount", "id"),
            "duration": ("itinerary__duration_minutes", "total_amount"),
            "departure": ("itinerary__departure_utc", "total_amount"),
        }.get(sort, ("total_amount", "id"))

        return queryset.order_by(*ordering)


@extend_schema(tags=["search"])
class OfferDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: OfferSerializer})
    def get(self, request, offer_id):
        """Re-validate an offer: signature, expiry, identity.

        Returns 409 ``offer_expired`` or ``offer_invalid`` rather than a stale price.
        """
        offer = load_offer(offer_id)
        return Response(OfferSerializer(offer).data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["search"],
    parameters=[
        OpenApiParameter("origin", str, required=True),
        OpenApiParameter("destination", str, required=True),
        OpenApiParameter("month", str, required=True, description="YYYY-MM"),
    ],
    responses={200: CalendarEntrySerializer(many=True)},
)
class FareCalendarView(APIView):
    """Cheapest fare per day for a month.

    Reads offers already produced by real searches rather than pricing 30 days on demand: the
    grid is a browsing aid, not a quotable price.
    """

    permission_classes = [AllowAny]
    throttle_scope = "search"

    def get(self, request):
        origin = request.query_params.get("origin", "").upper()
        destination = request.query_params.get("destination", "").upper()
        month = request.query_params.get("month", "")

        if not (origin and destination and month):
            return Response(
                {"detail": "origin, destination and month are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            first = date.fromisoformat(f"{month}-01")
        except ValueError:
            return Response(
                {"detail": "month must be YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST
            )

        key = f"wf:calendar:{origin}:{destination}:{month}"
        if (cached := cache.get(key)) is not None:
            return Response(cached)

        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        rows = (
            SearchQuery.objects.filter(
                origin=origin,
                destination=destination,
                depart_date__gte=first,
                depart_date__lte=last,
                offers__isnull=False,
            )
            .values("depart_date")
            .annotate(cheapest=Min("offers__total_amount"))
            .order_by("depart_date")
        )

        by_day = {row["depart_date"]: row["cheapest"] for row in rows}
        payload = [
            {
                "date": first + timedelta(days=offset),
                "cheapest": (
                    {"amount": str(by_day[first + timedelta(days=offset)]), "currency": "USD"}
                    if (first + timedelta(days=offset)) in by_day
                    else None
                ),
            }
            for offset in range((last - first).days + 1)
        ]

        data = CalendarEntrySerializer(payload, many=True).data
        cache.set(key, data, CALENDAR_CACHE_SECONDS)
        return Response(data)
