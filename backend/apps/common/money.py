from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


class CurrencyMismatch(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Money:
    """An amount bound to its currency. Never a float — see CLAUDE.md invariant 2."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(self, "amount", self.amount.quantize(CENTS, ROUND_HALF_UP))
        object.__setattr__(self, "currency", self.currency.upper())

    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount <= other.amount

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def minor_units(self) -> int:
        return int((self.amount * 100).to_integral_value(ROUND_HALF_UP))

    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(Decimal("0.00"), currency)

    @classmethod
    def from_minor_units(cls, units: int, currency: str) -> "Money":
        return cls(Decimal(units) / 100, currency)

    def as_dict(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency}

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


def total(items: list[Money], currency: str) -> Money:
    result = Money.zero(currency)
    for item in items:
        result = result + item
    return result
