import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

HEADER = "HTTP_X_REQUEST_ID"


class RequestIDMiddleware:
    """Binds a request id used by problem details, structured logs and the ClickHouse access log."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.request_id = request.META.get(HEADER) or uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
