from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Min
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.idempotency import idempotent
from apps.pricing.constants import TripType
from apps.pricing.services.refunds import quote_refund

from .models import Offer, SearchQuery
from .selectors import booking_for, guest_booking
from .serializers import (
    BookingCreateSerializer,
    BookingSerializer,
    CalendarEntrySerializer,
    CancelRequestSerializer,
    CancelResponseSerializer,
    ChangeConfirmResponseSerializer,
    ChangeQuoteSerializer,
    ChangeRequestSerializer,
    OfferSerializer,
    SearchRequestSerializer,
    SearchResponseSerializer,
)
from .services.booking import ContactDetails, create_booking
from .services.cancel import cancel_booking, is_voidable
from .services.change import confirm_change, quote_change
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
    queryset = Offer.objects.none()  # schema introspection has no URL kwargs

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Offer.objects.none()
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


@extend_schema(tags=["bookings"])
class BookingCreateView(APIView):
    """Turn an offer into a held PNR.

    Public: a traveller books before signing in more often than after. An authenticated call
    attaches the booking to the account, an anonymous one is retrievable with PNR + surname.
    """

    permission_classes = [AllowAny]
    throttle_scope = "booking_create"

    @extend_schema(
        request=BookingCreateSerializer,
        responses={201: BookingSerializer},
        description=(
            "Re-validates the offer's signature and expiry, re-reads availability under lock, "
            "holds the seats and mints a PNR. Requires an Idempotency-Key header."
        ),
    )
    @idempotent(scope="booking_create")
    def post(self, request):
        offer = load_offer(request.data.get("offer_id"))

        serializer = BookingCreateSerializer(
            data=request.data,
            context={"request": request, "reference_date": _reference_date(offer)},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        booking = create_booking(
            offer,
            data["passengers"],
            ContactDetails(
                email=data["contact"]["email"], phone=data["contact"].get("phone", "")
            ),
            user=request.user,
        )

        return Response(
            BookingSerializer(booking).data,
            status=status.HTTP_201_CREATED,
            headers={"ETag": f'"{booking.version}"'},
        )


@extend_schema(
    tags=["bookings"],
    parameters=[
        OpenApiParameter(
            "last_name",
            str,
            description="Required for guest retrieval; ignored when authenticated as the owner.",
        )
    ],
    responses={200: BookingSerializer},
)
class BookingDetailView(APIView):
    """Retrieve a booking by PNR.

    Owner or staff get it from the ownership-filtered selector; everyone else must supply the
    lead surname, and gets a 404 — never a 403 — when it does not match, so the endpoint cannot
    be used to confirm that a PNR exists.
    """

    permission_classes = [AllowAny]

    def get_throttles(self):
        if not (self.request.user and self.request.user.is_authenticated):
            self.throttle_scope = "guest_retrieve"
        return super().get_throttles()

    def get(self, request, pnr):
        booking = booking_for(request.user, pnr)

        if booking is None:
            booking = guest_booking(pnr, request.query_params.get("last_name", ""))

        if booking is None:
            raise NotFound("No booking matches those details.")

        return Response(
            BookingSerializer(booking).data, headers={"ETag": f'"{booking.version}"'}
        )


def _reference_date(offer: Offer) -> date:
    """Passenger age is judged at the return date, or the last flown date one-way."""
    search = offer.search_query
    if search.return_date:
        return search.return_date

    arrival = offer.itinerary.get("arrival_utc")
    return date.fromisoformat(arrival[:10]) if arrival else search.depart_date


@extend_schema(
    tags=["bookings"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    request=CancelRequestSerializer,
    responses={200: CancelResponseSerializer},
)
class BookingCancelView(APIView):
    """Cancel a booking and quote the refund.

    ``quote_only`` returns the penalty without cancelling, so the traveller can see what a
    cancellation costs before committing to it.
    """

    permission_classes = [AllowAny]
    throttle_scope = "payment"

    @idempotent(scope="booking_cancel")
    def post(self, request, pnr):
        booking = _owned_booking_or_404(request, pnr)

        serializer = CancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["quote_only"]:
            return Response(
                {
                    "booking": BookingSerializer(booking).data,
                    "quote": quote_refund(booking).as_dict(),
                    "voided": is_voidable(booking),
                    "refund_id": None,
                    "refund_status": None,
                }
            )

        result = cancel_booking(
            booking, actor=request.user, reason=data.get("reason", "")
        )

        return Response(
            {
                "booking": BookingSerializer(result.booking).data,
                "quote": result.quote.as_dict(),
                "voided": result.voided,
                "refund_id": str(result.refund.public_id) if result.refund else None,
                "refund_status": result.refund.status if result.refund else None,
            }
        )


@extend_schema(
    tags=["bookings"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    request=ChangeRequestSerializer,
    responses={200: ChangeQuoteSerializer},
)
class BookingChangeQuoteView(APIView):
    """Price an exchange onto a new offer. Changes nothing."""

    permission_classes = [AllowAny]
    throttle_scope = "payment"

    def post(self, request, pnr):
        booking = _owned_booking_or_404(request, pnr)

        serializer = ChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        offer = load_offer(serializer.validated_data["offer_id"])
        return Response(quote_change(booking, offer).as_dict())


@extend_schema(
    tags=["bookings"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    request=ChangeRequestSerializer,
    responses={200: ChangeConfirmResponseSerializer},
)
class BookingChangeConfirmView(APIView):
    """Move the booking onto the new itinerary.

    The new seats are taken and the booking becomes `CHANGE_PENDING`. Anything owed is collected
    through the ordinary payment flow, which triggers the reissue; when nothing is owed the
    exchange completes immediately.
    """

    permission_classes = [AllowAny]
    throttle_scope = "payment"

    @idempotent(scope="booking_change")
    def post(self, request, pnr):
        booking = _owned_booking_or_404(request, pnr)

        serializer = ChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        offer = load_offer(serializer.validated_data["offer_id"])
        booking, quote = confirm_change(booking, offer, actor=request.user)

        return Response(
            {"booking": BookingSerializer(booking).data, "quote": quote.as_dict()}
        )


def _owned_booking_or_404(request, pnr: str):
    booking = booking_for(request.user, pnr) or guest_booking(
        pnr, request.data.get("last_name", "") or request.query_params.get("last_name", "")
    )
    if booking is None:
        raise NotFound("No booking matches those details.")
    return booking
