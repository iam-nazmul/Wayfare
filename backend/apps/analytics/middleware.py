import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .events import push

SKIP_PREFIXES = ("/static", "/healthz", "/readyz", "/admin/jsi18n")


class RequestLogMiddleware:
    """Feeds wayfare.api_request_log. Buffered, never synchronous to ClickHouse."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith(SKIP_PREFIXES):
            return self.get_response(request)

        started = time.perf_counter()
        response = self.get_response(request)
        duration_ms = int((time.perf_counter() - started) * 1000)

        user = getattr(request, "user", None)
        push(
            "api_request",
            {
                "request_id": getattr(request, "request_id", ""),
                "method": request.method,
                "path": request.path,
                "route": getattr(getattr(request, "resolver_match", None), "route", "") or "",
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user.pk if user is not None and user.is_authenticated else None,
                "ip": request.META.get("REMOTE_ADDR", ""),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:512],
            },
        )
        return response
