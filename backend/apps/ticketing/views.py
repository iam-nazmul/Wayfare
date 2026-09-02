from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .selectors import tickets_for
from .serializers import TicketSerializer


@extend_schema(
    tags=["ticketing"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    responses={200: TicketSerializer(many=True)},
)
class BookingTicketListView(APIView):
    """E-tickets and coupon status for one booking.

    Returns an empty list rather than a 404 for a booking with no tickets yet — the client
    polls this while `issue_tickets` runs.
    """

    permission_classes = [AllowAny]

    def get(self, request, pnr):
        tickets = tickets_for(request.user, pnr, request.query_params.get("last_name", ""))
        return Response(TicketSerializer(tickets, many=True).data)
