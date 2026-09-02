from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.common.money import Money

#: Cancellation penalty as a fraction of the base fare, by time left before the first departure.
#: SPEC.md §6.4 requires a ladder but does not fix the steps; these are the published rule, and
#: §14 acceptance checks the boundaries, so change them here and nowhere else.
PENALTY_LADDER: tuple[tuple[timedelta, Decimal], ...] = (
    (timedelta(days=7), Decimal("0.00")),
    (timedelta(days=1), Decimal("0.25")),
    (timedelta(0), Decimal("0.50")),
)

#: Past departure the fare is gone: a no-show refunds nothing but the refundable taxes.
NO_SHOW_PENALTY = Decimal("1.00")


@dataclass(frozen=True, slots=True)
class RefundQuote:
    currency: str
    paid: Money
    penalty: Money
    non_refundable_tax: Money
    refundable: Money
    refundable_fare: bool
    reason: str = ""
    tax_lines: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "paid": self.paid.as_dict(),
            "penalty": self.penalty.as_dict(),
            "non_refundable_tax": self.non_refundable_tax.as_dict(),
            "refundable": self.refundable.as_dict(),
            "refundable_fare": self.refundable_fare,
            "reason": self.reason,
        }


def penalty_rate(departure, *, now=None) -> Decimal:
    """The ladder step in force for a given departure.

    Boundaries are inclusive of the longer window: exactly 7 days out is still the free step,
    which is what a passenger reading the fare rule expects.
    """
    remaining = departure - (now or timezone.now())

    if remaining < timedelta(0):
        return NO_SHOW_PENALTY

    for threshold, rate in PENALTY_LADDER:
        if remaining >= threshold:
            return rate

    return NO_SHOW_PENALTY


def quote_refund(booking, *, now=None) -> RefundQuote:
    """What a cancellation would return, before anyone approves it.

    ``refundable = paid - penalty - non-refundable taxes`` (SPEC.md §6.4). A non-refundable fare
    still returns the taxes that are themselves refundable — the airline keeps the fare, not the
    government's money.
    """
    currency = booking.currency
    paid = Money(Decimal(booking.paid_amount), currency)

    if paid.amount <= 0:
        return RefundQuote(
            currency=currency,
            paid=paid,
            penalty=Money.zero(currency),
            non_refundable_tax=Money.zero(currency),
            refundable=Money.zero(currency),
            refundable_fare=False,
            reason="Nothing has been paid on this booking.",
        )

    family = _fare_family(booking)
    refundable_fare = bool(family and family.refundable)
    base = Money(Decimal(booking.base_amount), currency)

    departure = _first_departure(booking)
    rate = penalty_rate(departure, now=now) if departure else NO_SHOW_PENALTY

    if refundable_fare:
        penalty = base * rate + Money(Decimal(family.refund_fee), currency)
        reason = f"{family.name}: {int(rate * 100)}% fare penalty plus the refund fee."
    else:
        # The fare itself is forfeit; only refundable taxes come back.
        penalty = base
        reason = (
            f"{family.name} is non-refundable — only refundable taxes are returned."
            if family
            else "This fare is non-refundable — only refundable taxes are returned."
        )

    withheld_tax, lines = _non_refundable_tax(booking, currency)

    # Fees are the agency's, never returned, so they sit with the withheld amount.
    withheld_tax = withheld_tax + Money(Decimal(booking.fee_amount), currency)

    refundable = paid - penalty - withheld_tax
    if refundable.amount < 0:
        refundable = Money.zero(currency)
    if penalty.amount > paid.amount:
        penalty = paid

    return RefundQuote(
        currency=currency,
        paid=paid,
        penalty=penalty,
        non_refundable_tax=withheld_tax,
        refundable=refundable,
        refundable_fare=refundable_fare,
        reason=reason,
        tax_lines=lines,
    )


def _fare_family(booking):
    segment = booking.segments.select_related("fare_family").first()
    return segment.fare_family if segment else None


def _first_departure(booking):
    segment = booking.segments.select_related("flight").order_by("sequence").first()
    return segment.flight.departure_utc if segment else None


def _non_refundable_tax(booking, currency: str) -> tuple[Money, list[dict]]:
    """Sum the tax lines the booking was sold with that do not come back.

    Reads the breakdown stored on the booking rather than re-deriving it from today's tax
    rules: a rule edited after the sale must not change what was already charged.
    """
    lines = booking.price_breakdown.get("tax_lines", []) if booking.price_breakdown else []

    if not lines:
        # Nothing recorded (a booking made before the breakdown was stored): withhold all tax,
        # which is the conservative reading of the fare rule rather than a guess in the
        # passenger's favour that finance would have to claw back.
        return Money(Decimal(booking.tax_amount), currency), []

    withheld = Money.zero(currency)
    for line in lines:
        if not line.get("refundable", False):
            amount = line.get("amount", {})
            withheld = withheld + Money(Decimal(str(amount.get("amount", "0"))), currency)

    return withheld, lines
