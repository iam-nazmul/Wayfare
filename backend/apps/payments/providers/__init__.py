from functools import cache

from django.conf import settings

from .base import (
    ChargeResult,
    IntentResult,
    PaymentProvider,
    RefundResult,
    WebhookEvent,
    WebhookVerificationFailed,
)
from .sandbox import SandboxProvider

__all__ = [
    "ChargeResult",
    "IntentResult",
    "PaymentProvider",
    "RefundResult",
    "WebhookEvent",
    "WebhookVerificationFailed",
    "get_provider",
]

_PROVIDERS = {"sandbox": SandboxProvider}


@cache
def get_provider(name: str = "") -> PaymentProvider:
    key = (name or settings.PAYMENT_PROVIDER).lower()
    try:
        return _PROVIDERS[key]()
    except KeyError:
        raise NotImplementedError(f"No payment provider named {key!r} is configured.") from None
