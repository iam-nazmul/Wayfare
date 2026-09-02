import hashlib
import hmac
import json
import secrets

from django.conf import settings

from apps.common.money import Money

from ..constants import IntentStatus, PaymentStatus, ThreeDsStatus
from .base import (
    ChargeResult,
    IntentResult,
    RefundResult,
    WebhookEvent,
    WebhookVerificationFailed,
)

#: Deterministic outcomes keyed off the test card (SPEC.md §5.7). The number is used to pick a
#: branch and is never returned, stored or logged — only the brand and last four survive.
OUTCOMES = {
    "4242424242424242": "succeed",
    "4000000000000002": "decline",
    "4000000000003220": "three_ds",
}

DEFAULT_OUTCOME = "succeed"


def brand_for(card_number: str) -> str:
    if card_number.startswith("4"):
        return "VISA"
    if card_number[:2] in {"51", "52", "53", "54", "55"}:
        return "MASTERCARD"
    if card_number[:2] in {"34", "37"}:
        return "AMEX"
    return "CARD"


class SandboxProvider:
    """Stands in for a real PSP in development and tests.

    It behaves like one on the wire: intents are confirmed out of band and the outcome comes
    back through the same signed webhook the Stripe implementation will use, so the code path
    under test is the production one.
    """

    name = "sandbox"

    def create_intent(
        self, *, amount: Money, booking_ref: str, idempotency_key: str, metadata: dict
    ) -> IntentResult:
        token = secrets.token_hex(12)
        return IntentResult(
            intent_id=f"sbx_pi_{token}",
            client_secret=f"sbx_pi_{token}_secret_{secrets.token_hex(8)}",
            status=IntentStatus.REQUIRES_PAYMENT,
            three_ds_status=ThreeDsStatus.NOT_REQUIRED,
        )

    def confirm(self, intent_id: str, card_number: str) -> ChargeResult:
        """Sandbox-only: what the provider's SDK would do inside the browser."""
        digits = "".join(character for character in card_number if character.isdigit())
        outcome = OUTCOMES.get(digits, DEFAULT_OUTCOME)
        last4 = digits[-4:]

        if outcome == "decline":
            return ChargeResult(
                charge_id=f"sbx_ch_{secrets.token_hex(10)}",
                status=PaymentStatus.FAILED,
                card_brand=brand_for(digits),
                card_last4=last4,
                failure_code="card_declined",
                failure_message="The card was declined.",
            )

        return ChargeResult(
            charge_id=f"sbx_ch_{secrets.token_hex(10)}",
            status=PaymentStatus.CAPTURED,
            card_brand=brand_for(digits),
            card_last4=last4,
        )

    def requires_three_ds(self, card_number: str) -> bool:
        digits = "".join(character for character in card_number if character.isdigit())
        return OUTCOMES.get(digits) == "three_ds"

    def capture(self, intent_id: str, amount: Money | None = None) -> ChargeResult:
        return ChargeResult(
            charge_id=f"sbx_ch_{secrets.token_hex(10)}", status=PaymentStatus.CAPTURED
        )

    def void(self, intent_id: str) -> ChargeResult:
        return ChargeResult(charge_id=intent_id, status=IntentStatus.CANCELLED)

    def refund(self, charge_id: str, amount: Money, idempotency_key: str) -> RefundResult:
        return RefundResult(refund_id=f"sbx_re_{secrets.token_hex(10)}", status="PROCESSED")

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret(), payload, hashlib.sha256).hexdigest()

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        if not hmac.compare_digest(self.sign(payload), signature or ""):
            raise WebhookVerificationFailed("Signature mismatch.")

        body = json.loads(payload)
        return WebhookEvent(
            event_id=body["id"], event_type=body["type"], payload=body.get("data", {})
        )

    @staticmethod
    def _secret() -> bytes:
        return (settings.STRIPE_WEBHOOK_SECRET or settings.SECRET_KEY).encode()
