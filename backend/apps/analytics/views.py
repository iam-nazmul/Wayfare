import csv
import hashlib
import json
from io import StringIO

from django.core.cache import cache
from django.http import StreamingHttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import OpsPermission
from apps.common.renderers import CSVRenderer

from .devices import device_type
from .events import push
from .reports import REPORTS
from .serializers import (
    CollectBatchSerializer,
    ReportResponseSerializer,
    ReportWindowSerializer,
)

#: SPEC.md §9.5 — every report endpoint is cached for five minutes.
REPORT_CACHE_SECONDS = 300


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
        device = device_type(request.headers.get("User-Agent", ""))

        for event in serializer.validated_data["events"]:
            push("clickstream", {**event, "user_id": user_id,
                                 "device_type": device,
                                 "ip_country": request.headers.get("CF-IPCountry", "")})
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["ops"],
    parameters=[
        OpenApiParameter("date_from", OpenApiTypes.DATE, description="Defaults to 30 days ago"),
        OpenApiParameter("date_to", OpenApiTypes.DATE, description="Defaults to today"),
        OpenApiParameter("origin", str, description="fare-trend only"),
        OpenApiParameter("destination", str, description="fare-trend only"),
    ],
    responses={200: ReportResponseSerializer},
    description=(
        "Operational reports (SPEC.md §9.5). Cached for five minutes; send "
        "`Accept: text/csv` for a CSV stream instead of JSON."
    ),
)
class OpsReportView(APIView):
    """One endpoint per report slug, sharing the window, cache and CSV handling.

    Reports are read-only and read ClickHouse (except load-factor, which needs live inventory),
    so they are never on a booking path — a slow report cannot slow down a sale.
    """

    permission_classes = [OpsPermission]
    renderer_classes = [JSONRenderer, CSVRenderer]

    def get(self, request, slug):
        report_fn = REPORTS.get(slug)
        if report_fn is None:
            raise NotFound(f"No report named {slug!r}.")

        window = ReportWindowSerializer(data=request.query_params)
        window.is_valid(raise_exception=True)
        params = window.validated_data

        filters = {
            "origin": request.query_params.get("origin", ""),
            "destination": request.query_params.get("destination", ""),
        }
        key = _cache_key(slug, params, filters)

        payload = cache.get(key)
        if payload is None:
            report = report_fn(params["date_from"], params["date_to"], **filters)
            payload = report.as_dict()
            cache.set(key, payload, REPORT_CACHE_SECONDS)

        if _wants_csv(request):
            return _csv_response(slug, payload)

        return Response({"report": slug, **params_as_dict(params), **payload})


def params_as_dict(params: dict) -> dict:
    return {"date_from": params["date_from"], "date_to": params["date_to"]}


def _cache_key(slug: str, params: dict, filters: dict) -> str:
    digest = hashlib.sha256(
        json.dumps({**params_as_dict(params), **filters}, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    return f"wf:report:{slug}:{digest}"


def _wants_csv(request) -> bool:
    return "text/csv" in request.headers.get("Accept", "")


def _csv_response(slug: str, payload: dict) -> StreamingHttpResponse:
    """Streamed, not built in memory: a 400-day revenue pull is not a small string."""

    def rows():
        buffer = StringIO()
        writer = csv.writer(buffer)

        writer.writerow(payload["columns"])
        yield _drain(buffer)

        for row in payload["rows"]:
            writer.writerow(row)
            yield _drain(buffer)

    response = StreamingHttpResponse(rows(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
    return response


def _drain(buffer: StringIO) -> str:
    value = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return value
