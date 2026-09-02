from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.booking.serializers import BookingSerializer
from apps.common.idempotency import idempotent
from apps.common.permissions import OpsPermission

from .selectors import booking_or_none, open_disruptions, option_for, rebook_options_for
from .serializers import (
    DisruptionSerializer,
    RebookOptionSerializer,
    RebookRequestSerializer,
)
from .services.rebook import accept_rebooking


def _booking_or_404(request, pnr: str):
    booking = booking_or_none(
        request.user,
        pnr,
        request.data.get("last_name", "") or request.query_params.get("last_name", ""),
    )
    if booking is None:
        raise NotFound("No booking matches those details.")
    return booking


@extend_schema(
    tags=["disruption"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    responses={200: RebookOptionSerializer(many=True)},
)
class RebookOptionListView(APIView):
    """Alternatives offered after a disruption.

    Returns `[]` for an undisrupted booking rather than a 404 — the client asks routinely.
    """

    permission_classes = [AllowAny]

    def get(self, request, pnr):
        booking = _booking_or_404(request, pnr)
        return Response(
            RebookOptionSerializer(rebook_options_for(booking), many=True).data
        )


@extend_schema(
    tags=["disruption"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    request=RebookRequestSerializer,
    responses={200: BookingSerializer},
)
class RebookView(APIView):
    """Take one of the offered alternatives.

    Availability is re-read under lock: an option is a suggestion, not a reservation, so a
    flight that filled up in the meantime returns 409 rather than overselling.
    """

    permission_classes = [AllowAny]
    throttle_scope = "payment"

    @idempotent(scope="booking_rebook")
    def post(self, request, pnr):
        booking = _booking_or_404(request, pnr)

        serializer = RebookRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        option = option_for(booking, serializer.validated_data["option_id"])
        if option is None:
            raise NotFound("No such rebooking option for this booking.")

        booking = accept_rebooking(booking, option, actor=request.user)
        return Response(BookingSerializer(booking).data)


@extend_schema(
    tags=["ops"],
    responses={200: DisruptionSerializer(many=True)},
)
class OpsDisruptionListView(APIView):
    """Open disruptions, newest first. Ops staff only."""

    permission_classes = [OpsPermission]

    def get(self, request):
        return Response(DisruptionSerializer(open_disruptions(), many=True).data)
