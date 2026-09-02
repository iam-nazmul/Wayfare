from dataclasses import dataclass, field
from typing import Protocol

from apps.common.money import Money


@dataclass(frozen=True, slots=True)
class IntentResult:
    intent_id: str
    client_secret: str
    status: str
    three_ds_status: str


@dataclass(frozen=True, slots=True)
class ChargeResult:
    charge_id: str
    status: str
    card_brand: str = ""
    card_last4: str = ""
    failure_code: str = ""
    failure_message: str = ""


@dataclass(frozen=True, slots=True)
class RefundResult:
    refund_id: str
    status: str


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    event_id: str
    event_type: str
    payload: dict = field(default_factory=dict)


class WebhookVerificationFailed(Exception):
    """The signature did not match. Never trust the body after this."""


class PaymentProvider(Protocol):
    """See SPEC.md §5.7. Implementations must never return or log a PAN or CVV."""

    name: str

    def create_intent(
        self, *, amount: Money, booking_ref: str, idempotency_key: str, metadata: dict
    ) -> IntentResult: ...

    def capture(self, intent_id: str, amount: Money | None = None) -> ChargeResult: ...

    def void(self, intent_id: str) -> ChargeResult: ...

    def refund(
        self, charge_id: str, amount: Money, idempotency_key: str
    ) -> RefundResult: ...

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent: ...
