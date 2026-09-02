import functools
import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.response import Response

from .exceptions import IdempotencyInProgress, IdempotencyKeyReuse
from .models import IdempotencyKey

HEADER = "HTTP_IDEMPOTENCY_KEY"

#: A claim that has been taken but whose work has not finished. Not a real HTTP status.
IN_PROGRESS = 0

#: How long a claim may sit unfinished before it is assumed dead. Without a takeover, a request
#: whose process died mid-flight would poison that key until the daily purge.
STALE_AFTER = timedelta(seconds=60)


def body_hash(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def idempotent(scope: str):
    """Replay-safe POST handling.

    Same key + same body returns the stored response; same key + different body is a 422; the
    same key arriving twice at once does the work once.

    A missing key is allowed through — enforce presence in the view when the contract requires it.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            key = request.META.get(HEADER)
            if not key:
                return view_func(self, request, *args, **kwargs)

            digest = body_hash(request.data)
            claim, replay = _claim(scope, key, digest)
            if replay is not None:
                return replay

            try:
                response = view_func(self, request, *args, **kwargs)
            except Exception:
                # The work did not happen, so the key must not stay claimed — the caller has to
                # be able to retry with it.
                _release(claim)
                raise

            if 200 <= response.status_code < 300:
                response = _render(response)
                IdempotencyKey.objects.filter(pk=claim.pk).update(
                    response_status=response.status_code, response_body=response.data
                )
            else:
                _release(claim)

            return response

        return wrapper

    return decorator


def _claim(scope: str, key: str, digest: str) -> tuple[IdempotencyKey | None, Response | None]:
    """Take ownership of the key *before* the work starts.

    Writing the row afterwards lets two concurrent requests with one key both run the view and
    both do the work; one booking is then orphaned, holding inventory nobody will ever pay for.
    The unique index decides ownership up front instead.

    Returns ``(claim, None)`` when this request owns the work, or ``(None, response)`` when a
    finished claim can simply be replayed.
    """
    try:
        with transaction.atomic():
            return (
                IdempotencyKey.objects.create(
                    scope=scope,
                    key=key,
                    request_hash=digest,
                    response_status=IN_PROGRESS,
                    response_body={},
                ),
                None,
            )
    except IntegrityError:
        pass

    existing = IdempotencyKey.objects.filter(scope=scope, key=key).first()
    if existing is None:
        # Purged between the failed insert and this read; the caller can just try again.
        raise IdempotencyInProgress(f"Key {key} is in use. Retry in a moment.")

    if existing.request_hash != digest:
        raise IdempotencyKeyReuse(
            f"Key {key} was already used for a different {scope} request."
        )

    if existing.response_status != IN_PROGRESS:
        return None, Response(existing.response_body, status=existing.response_status)

    if timezone.now() - existing.created_at < STALE_AFTER:
        raise IdempotencyInProgress(
            f"A {scope} request with key {key} is already running. Retry in a moment."
        )

    # The owner died mid-flight. Guarded on the status so only one taker wins.
    taken = IdempotencyKey.objects.filter(
        pk=existing.pk, response_status=IN_PROGRESS
    ).update(created_at=timezone.now())
    if not taken:
        raise IdempotencyInProgress(f"Key {key} is in use. Retry in a moment.")

    return existing, None


def _release(claim: IdempotencyKey) -> None:
    """Give an unfinished claim back so the same key can be retried."""
    IdempotencyKey.objects.filter(pk=claim.pk, response_status=IN_PROGRESS).delete()


def _render(response: Response) -> Response:
    if not getattr(response, "_wayfare_rendered", False):
        response.__class__ = Response
        response._wayfare_rendered = True
    return response
