from rest_framework import serializers

from apps.common.fields import MoneyField

from .models import Payment, PaymentIntent, Refund


class PaymentIntentSerializer(serializers.ModelSerializer):
    intent_id = serializers.UUIDField(source="public_id", read_only=True)
    amount = MoneyField("amount", read_only=True, source="*")

    class Meta:
        model = PaymentIntent
        fields = [
            "intent_id", "provider", "provider_intent_id", "amount", "status",
            "client_secret", "three_ds_status", "expires_at",
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    payment_id = serializers.UUIDField(source="public_id", read_only=True)
    amount = MoneyField("amount", read_only=True, source="*")

    class Meta:
        model = Payment
        fields = [
            "payment_id", "method", "provider", "amount", "status",
            "card_brand", "card_last4", "captured_at", "failure_code", "failure_message",
        ]
        read_only_fields = fields


class SandboxConfirmSerializer(serializers.Serializer):
    """Stands in for the provider's browser SDK.

    The card number is used to pick a deterministic sandbox outcome and is never stored, logged
    or echoed — only the brand and last four survive the call (CLAUDE.md invariant 9).
    """

    card_number = serializers.RegexField(r"^\d{12,19}$", write_only=True)

    def validate_card_number(self, value: str) -> str:
        return value.strip()


class RefundSerializer(serializers.ModelSerializer):
    refund_id = serializers.UUIDField(source="public_id", read_only=True)
    pnr = serializers.CharField(source="booking.pnr", read_only=True)
    amount = MoneyField("amount", read_only=True, source="*")
    penalty = MoneyField("penalty_amount", read_only=True, source="*")

    class Meta:
        model = Refund
        fields = [
            "refund_id", "pnr", "amount", "penalty", "status", "reason",
            "provider_refund_id", "processed_at", "created_at",
        ]
        read_only_fields = fields


class RefundDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
