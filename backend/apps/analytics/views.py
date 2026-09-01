from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .events import push
from .serializers import CollectBatchSerializer


class CollectView(APIView):
    """Clickstream sink for navigator.sendBeacon.

    AllowAny: the storefront is anonymous until checkout, so most funnel events have no user.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "collect"

    @extend_schema(request=CollectBatchSerializer, responses={204: None}, tags=["analytics"])
    def post(self, request):
        serializer = CollectBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and user.is_authenticated else None
        for event in serializer.validated_data["events"]:
            push("clickstream", {**event, "user_id": user_id,
                                 "ip_country": request.headers.get("CF-IPCountry", "")})
        return Response(status=status.HTTP_204_NO_CONTENT)
