from decimal import Decimal

from rest_framework import serializers

from .money import Money


class MoneyField(serializers.Field):
    """Serializes a (amount, currency) column pair as {"amount": "412.50", "currency": "USD"}.

    Use with ``source="*"`` so the field sees the whole instance::

        total = MoneyField("total_amount", source="*", read_only=True)
    """

    def __init__(self, amount_field: str, currency_field: str = "currency", **kwargs) -> None:
        self.amount_field = amount_field
        self.currency_field = currency_field
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, instance) -> dict[str, str] | None:
        amount = getattr(instance, self.amount_field, None)
        if amount is None:
            return None
        currency = getattr(instance, self.currency_field, None) or ""
        return Money(Decimal(amount), currency).as_dict()

    def to_internal_value(self, data) -> Money:
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object with amount and currency.")
        try:
            return Money(Decimal(str(data["amount"])), str(data["currency"]))
        except KeyError as exc:
            raise serializers.ValidationError(f"Missing {exc.args[0]}.") from exc
        except (ArithmeticError, ValueError) as exc:
            raise serializers.ValidationError("Invalid amount.") from exc


class MoneyOutputSerializer(serializers.Serializer):
    """Schema-only helper so drf-spectacular documents inline money objects."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
