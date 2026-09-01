import functools
import hashlib
import json

from django.db import IntegrityError, transaction
from rest_framework.response import Response

from .exceptions import IdempotencyKeyReuse
from .models import IdempotencyKey

HEADER = "HTTP_IDEMPOTENCY_KEY"


def body_hash(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def idempotent(scope: str):
    """Replay-safe POST handling.

    Same key + same body returns the stored response; same key + different body is a 422.
    A missing key is allowed through — enforce presence in the view when the contract requires it.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            key = request.META.get(HEADER)
            if not key:
                return view_func(self, request, *args, **kwargs)

            digest = body_hash(request.data)
            existing = IdempotencyKey.objects.filter(scope=scope, key=key).first()
            if existing is not None:
                if existing.request_hash != digest:
                    raise IdempotencyKeyReuse(
                        f"Key {key} was already used for a different {scope} request."
                    )
                return Response(existing.response_body, status=existing.response_status)

            response = view_func(self, request, *args, **kwargs)

            if 200 <= response.status_code < 300:
                response = _render(response)
                try:
                    with transaction.atomic():
                        IdempotencyKey.objects.create(
                            scope=scope,
                            key=key,
                            request_hash=digest,
                            response_status=response.status_code,
                            response_body=response.data,
                        )
                except IntegrityError:
                    # A concurrent request with the same key won the race; replay its answer.
                    stored = IdempotencyKey.objects.get(scope=scope, key=key)
                    if stored.request_hash != digest:
                        raise IdempotencyKeyReuse(f"Key {key} is in use.") from None
                    return Response(stored.response_body, status=stored.response_status)
            return response

        return wrapper

    return decorator


def _render(response: Response) -> Response:
    if not getattr(response, "_wayfare_rendered", False):
        response.__class__ = Response
        response._wayfare_rendered = True
    return response
