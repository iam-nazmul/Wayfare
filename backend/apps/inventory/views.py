from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.common.permissions import OpsPermission, OpsReadOnlyOrRole

from . import selectors
from .models import BookingClass, CabinConfig, Flight, FlightSchedule, Route, SeatMapTemplate
from .serializers import (
    CabinConfigSerializer,
    FlightDetailSerializer,
    FlightOpsSerializer,
    FlightScheduleSerializer,
    FlightSerializer,
    InventoryUpdateSerializer,
    MaterialiseSerializer,
    RouteSerializer,
    SeatMapTemplateSerializer,
    SeatSerializer,
)
from .services.cache import invalidate_flight
from .services.materialise import materialise_schedule


@extend_schema(tags=["catalog"])
class FlightSeatMapView(ListAPIView):
    """Public seat map for a flight. Prices come from the seat rows, not a pricing call."""

    serializer_class = SeatSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        flight = Flight.objects.get(public_id=self.kwargs["public_id"])
        return selectors.seats_for(flight.id, self.request.query_params.get("cabin", ""))


@extend_schema(tags=["ops"])
class OpsScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = FlightScheduleSerializer
    permission_classes = [OpsReadOnlyOrRole]
    queryset = FlightSchedule.objects.select_related(
        "airline", "aircraft", "route__origin_airport", "route__destination_airport"
    ).order_by("airline_id", "flight_number")

    @extend_schema(request=MaterialiseSerializer, responses={202: None})
    @action(detail=True, methods=["post"])
    def materialise(self, request, pk=None):
        """Generate dated flights for a window. Re-running is safe — existing dates are skipped."""
        serializer = MaterialiseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        schedule = self.get_object()
        start = timezone.now().date()
        end = start + timedelta(days=serializer.validated_data["days"])
        created, skipped = materialise_schedule(schedule, start, end)

        return Response(
            {"created": created, "skipped": skipped, "window": [str(start), str(end)]},
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(tags=["ops"])
class OpsRouteViewSet(viewsets.ModelViewSet):
    serializer_class = RouteSerializer
    permission_classes = [OpsReadOnlyOrRole]
    queryset = Route.objects.select_related(
        "airline", "origin_airport", "destination_airport"
    ).order_by("airline_id")


@extend_schema(tags=["ops"])
class OpsSeatMapTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = SeatMapTemplateSerializer
    permission_classes = [OpsReadOnlyOrRole]
    queryset = SeatMapTemplate.objects.select_related("aircraft").order_by("name")


@extend_schema(tags=["ops"])
class OpsFlightViewSet(viewsets.ModelViewSet):
    permission_classes = [OpsReadOnlyOrRole]
    lookup_field = "public_id"
    http_method_names = ["get", "patch", "head", "options"]
    filterset_fields = ["status", "airline", "origin_airport", "destination_airport"]

    def get_queryset(self):
        return selectors.flights_base().order_by("departure_utc")

    def get_serializer_class(self):
        if self.action == "partial_update":
            return FlightOpsSerializer
        if self.action == "retrieve":
            return FlightDetailSerializer
        return FlightSerializer

    def perform_update(self, serializer) -> None:
        flight = serializer.save()
        Flight.objects.filter(pk=flight.pk).update(version=flight.version + 1)
        invalidate_flight(flight.pk)

    @extend_schema(
        request=InventoryUpdateSerializer,
        responses={200: CabinConfigSerializer(many=True)},
    )
    @action(detail=True, methods=["get", "patch"])
    def inventory(self, request, public_id=None):
        """Read or adjust cabin capacity and the RBD ladder.

        One action serves both verbs: two actions sharing a url_path collide in the router.

        Capacity may not drop below what is already sold and held, and an RBD authorisation may
        not drop below its own sold count — either would put the flight into a state the
        check constraints reject.
        """
        flight = self.get_object()

        if request.method == "GET":
            cabins = flight.cabins.prefetch_related("booking_classes").order_by("cabin")
            return Response(CabinConfigSerializer(cabins, many=True).data)

        serializer = InventoryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            cabin_config = (
                CabinConfig.objects.select_for_update()
                .get(flight=flight, cabin=data["cabin"])
            )

            if "capacity" in data:
                floor = cabin_config.seats_sold + cabin_config.seats_held
                if data["capacity"] < floor:
                    return Response(
                        {"detail": f"Capacity cannot drop below {floor} sold and held seats."},
                        status=status.HTTP_409_CONFLICT,
                    )
                cabin_config.capacity = data["capacity"]

            if "oversell_allowance" in data:
                cabin_config.oversell_allowance = data["oversell_allowance"]
            cabin_config.save()

            for entry in data.get("booking_classes", []):
                booking_class = (
                    BookingClass.objects.select_for_update()
                    .filter(flight=flight, rbd=entry.get("rbd"))
                    .first()
                )
                if booking_class is None:
                    continue
                if "authorised" in entry:
                    if int(entry["authorised"]) < booking_class.sold:
                        return Response(
                            {"detail": f"Class {booking_class.rbd} already sold "
                                       f"{booking_class.sold} seats."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    booking_class.authorised = int(entry["authorised"])
                if "is_open" in entry:
                    booking_class.is_open = bool(entry["is_open"])
                booking_class.save(update_fields=["authorised", "is_open", "updated_at"])

        invalidate_flight(flight.pk)
        cabin_config.refresh_from_db()
        return Response(CabinConfigSerializer(cabin_config).data)


@extend_schema(tags=["ops"])
class OpsFlightManifestView(ListAPIView):
    """Passenger manifest. Returns seats until booking lands in M3."""

    serializer_class = SeatSerializer
    permission_classes = [OpsPermission]
    pagination_class = None

    def get_queryset(self):
        flight = Flight.objects.get(public_id=self.kwargs["public_id"])
        return selectors.seats_for(flight.id).exclude(status="AVAILABLE")
