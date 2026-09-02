import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import PaymentFailed
from apps.common.idempotency import idempotent

from .constants import IntentStatus, ThreeDsStatus
from .providers import WebhookVerificationFailed, get_provider
from .selectors import booking_or_none, intent_for, payments_for_booking
from .serializers import (
    PaymentIntentSerializer,
    PaymentSerializer,
    SandboxConfirmSerializer,
)
from .services.intents import create_payment_intent
from .services.webhooks import record_event
from .tasks import handle_payment_succeeded

logger = logging.getLogger("wayfare.payments")


def _booking_or_404(request, pnr: str):
    booking = booking_or_none(request.user, pnr, request.query_params.get("last_name", ""))
    if booking is None:
        raise NotFound("No booking matches those details.")
    return booking


@extend_schema(
    tags=["payments"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    request=None,
    responses={201: PaymentIntentSerializer},
)
class PaymentIntentCreateView(APIView):
    """Open a provider intent for a booking's balance.

    The response carries a ``client_secret``: the SPA sends the card straight to the provider
    with it, so no card data ever reaches Wayfare.
    """

    permission_classes = [AllowAny]
    throttle_scope = "payment"

    @idempotent(scope="payment_intent")
    def post(self, request, pnr):
        booking = _booking_or_404(request, pnr)
        intent = create_payment_intent(
            booking, idempotency_key=request.META.get("HTTP_IDEMPOTENCY_KEY", "")
        )
        return Response(
            PaymentIntentSerializer(intent).data, status=status.HTTP_201_CREATED
        )


@extend_schema(
    tags=["payments"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    responses={200: PaymentIntentSerializer},
)
class PaymentIntentDetailView(APIView):
    """Poll one intent. The booking itself is the source of truth for whether it is ticketed."""

    permission_classes = [AllowAny]

    def get(self, request, pnr, intent_id):
        intent = intent_for(
            request.user, pnr, intent_id, request.query_params.get("last_name", "")
        )
        if intent is None:
            raise NotFound("No payment intent matches those details.")
        return Response(PaymentIntentSerializer(intent).data)


@extend_schema(
    tags=["payments"],
    parameters=[OpenApiParameter("last_name", str, description="Required for guest access")],
    responses={200: PaymentSerializer(many=True)},
)
class PaymentListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pnr):
        booking = _booking_or_404(request, pnr)
        payments = payments_for_booking(booking)
        return Response(PaymentSerializer(payments, many=True).data)


@extend_schema(
    tags=["payments"],
    request=SandboxConfirmSerializer,
    responses={202: PaymentIntentSerializer},
    description=(
        "Sandbox only — stands in for the provider's browser SDK. Confirms an intent with a "
        "test card and emits the same signed webhook a real provider would."
    ),
)
class SandboxConfirmView(APIView):
    """Development stand-in for the provider SDK's confirm call.

    Deliberately produces the outcome through the *webhook* path rather than mutating the
    booking here, so development and production exercise the same code.
    """

    permission_classes = [AllowAny]
    throttle_scope = "payment"

    def post(self, request, pnr, intent_id):
        if settings.PAYMENT_PROVIDER != "sandbox":
            raise NotFound("Not available for this payment provider.")

        intent = intent_for(
            request.user, pnr, intent_id, request.data.get("last_name", "")
        )
        if intent is None:
            raise NotFound("No payment intent matches those details.")

        serializer = SandboxConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        card_number = serializer.validated_data["card_number"]

        if intent.status == IntentStatus.SUCCEEDED:
            return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_200_OK)
        if intent.expires_at <= timezone.now():
            raise PaymentFailed("This payment session has expired. Start again.")

        provider = get_provider("sandbox")

        if provider.requires_three_ds(card_number):
            intent.status = IntentStatus.REQUIRES_ACTION
            intent.three_ds_status = ThreeDsStatus.REQUIRED
            intent.save(update_fields=["status", "three_ds_status", "updated_at"])
            return Response(
                PaymentIntentSerializer(intent).data, status=status.HTTP_202_ACCEPTED
            )

        charge = provider.confirm(intent.provider_intent_id, card_number)
        del card_number  # nothing below this line may see it

        body, signature = _sandbox_callback(provider, intent, charge)
        event = record_event("sandbox", body, signature)
        if event is not None:
            transaction.on_commit(lambda: handle_payment_succeeded.delay(event.id))

        intent.refresh_from_db()
        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_202_ACCEPTED)


def _sandbox_callback(provider, intent, charge) -> tuple[bytes, str]:
    succeeded = not charge.failure_code
    body = json.dumps(
        {
            "id": f"sbx_evt_{charge.charge_id}",
            "type": "payment_intent.succeeded" if succeeded else "payment_intent.payment_failed",
            "data": {
                "intent_id": intent.provider_intent_id,
                "charge_id": charge.charge_id,
                "amount": str(intent.amount),
                "currency": intent.currency,
                "card_brand": charge.card_brand,
                "card_last4": charge.card_last4,
                "failure_code": charge.failure_code,
                "failure_message": charge.failure_message,
            },
        },
        sort_keys=True,
    ).encode()

    return body, provider.sign(body)


@extend_schema(
    tags=["payments"],
    request=None,
    responses={202: None},
    description="Provider callback. Signature-verified, unauthenticated, replay-safe.",
)
class PaymentWebhookView(APIView):
    """Provider callbacks land here.

    Unauthenticated by necessity — the provider has no session. The signature is the
    authentication, and `provider_event_id` uniqueness is what makes redelivery a no-op.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request, provider):
        signature = request.headers.get("X-Wayfare-Signature", "")

        try:
            event = record_event(provider, request.body, signature)
        except WebhookVerificationFailed:
            logger.warning("webhook_signature_rejected", extra={"provider": provider})
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except NotImplementedError:
            raise NotFound(f"No provider named {provider}.") from None

        if event is not None:
            transaction.on_commit(lambda: handle_payment_succeeded.delay(event.id))

        # 202 either way: a replay is a success from the provider's point of view.
        return Response(status=status.HTTP_202_ACCEPTED)
