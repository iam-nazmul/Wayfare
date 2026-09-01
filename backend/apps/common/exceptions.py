from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

ERROR_BASE = "https://wayfare.dev/errors/"


class DomainError(Exception):
    """Base for errors the API maps to a problem detail. See api-conventions.md."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "domain_error"
    title = "Request could not be completed"

    def __init__(self, detail: str = "", **extra: Any) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)


class OfferExpired(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "offer_expired"
    title = "This offer has expired"


class OfferInvalid(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "offer_invalid"
    title = "This offer is not valid"


class InventoryUnavailable(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "inventory_unavailable"
    title = "Requested seats are no longer available"


class InvalidTransition(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "invalid_transition"
    title = "That change is not allowed in the current state"


class IdempotencyKeyReuse(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "idempotency_key_reuse"
    title = "Idempotency key reused with a different request body"


class PaymentFailed(DomainError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "payment_failed"
    title = "Payment could not be completed"


class FareRuleViolation(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "fare_rule_violation"
    title = "Fare rules do not permit this"


class TransientError(Exception):
    """Retryable failure — Celery autoretries on this and nothing else."""


def _problem(
    *, status_code: int, code: str, title: str, detail: str, request=None, errors=None
) -> Response:
    body: dict[str, Any] = {
        "type": f"{ERROR_BASE}{code.replace('_', '-')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
    }
    request_id = getattr(request, "request_id", None) if request else None
    if request_id:
        body["request_id"] = request_id
    if errors:
        body["errors"] = errors
    return Response(body, status=status_code, content_type="application/problem+json")


def _flatten(detail: Any, prefix: str = "") -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if isinstance(detail, dict):
        for field, value in detail.items():
            errors.extend(_flatten(value, f"{prefix}.{field}" if prefix else str(field)))
    elif isinstance(detail, list):
        for item in detail:
            errors.extend(_flatten(item, prefix))
    else:
        errors.append({"field": prefix or "non_field_errors", "message": str(detail)})
    return errors


_DRF_CODES = {
    400: ("validation_error", "The request could not be validated"),
    401: ("authentication_required", "Authentication is required"),
    403: ("permission_denied", "You do not have access to this resource"),
    404: ("not_found", "Resource not found"),
    405: ("method_not_allowed", "Method not allowed"),
    409: ("conflict", "The request conflicts with the current state"),
    412: ("precondition_failed", "The resource has changed since you loaded it"),
    415: ("unsupported_media_type", "Unsupported media type"),
    429: ("rate_limited", "Too many requests"),
    500: ("server_error", "Something went wrong"),
}


def problem_detail_handler(exc: Exception, context: dict) -> Response | None:
    request = context.get("request")

    if isinstance(exc, DomainError):
        return _problem(
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            request=request,
            errors=exc.extra.get("errors"),
        )

    if isinstance(exc, Http404):
        code, title = _DRF_CODES[404]
        return _problem(
            status_code=404, code=code, title=title, detail="Resource not found", request=request
        )

    if isinstance(exc, PermissionDenied):
        code, title = _DRF_CODES[403]
        return _problem(
            status_code=403, code=code, title=title, detail=str(exc) or title, request=request
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    status_code = response.status_code
    code, title = _DRF_CODES.get(status_code, ("error", "Request failed"))

    # DRF hands validation problems back as 400; the contract calls them 422.
    errors = None
    detail = title
    data = response.data
    if status_code == 400:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        code, title = "validation_error", "The request could not be validated"
        errors = _flatten(data)
        detail = errors[0]["message"] if errors else title
    elif isinstance(data, dict) and "detail" in data:
        detail = str(data["detail"])

    return _problem(
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        request=request,
        errors=errors,
    )
