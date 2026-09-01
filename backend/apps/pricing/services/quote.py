from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.common.money import Money
from apps.inventory.models import Flight

from ..constants import (
    DEFAULT_PAX_DISCOUNT,
    CalcType,
    DiscountType,
    FeeScope,
    PassengerType,
    TaxScope,
)
from ..models import Fare, FeeRule, PromoCode, TaxRule


@dataclass(frozen=True, slots=True)
class PassengerCount:
    adults: int = 1
    children: int = 0
    infants: int = 0

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants

    @property
    def seated(self) -> int:
        """Infants travel on a lap and consume no seat inventory."""
        return self.adults + self.children

    def as_types(self) -> list[tuple[str, int]]:
        return [
            (PassengerType.ADULT, self.adults),
            (PassengerType.CHILD, self.children),
            (PassengerType.INFANT, self.infants),
        ]


@dataclass
class SegmentPrice:
    flight_id: int
    cabin: str
    rbd: str
    fare_id: int
    fare_basis: str
    fare_family_id: int
    base: Money


@dataclass
class PriceBreakdown:
    currency: str
    segments: list[SegmentPrice] = field(default_factory=list)
    base_amount: Money = None  # type: ignore[assignment]
    tax_amount: Money = None  # type: ignore[assignment]
    fee_amount: Money = None  # type: ignore[assignment]
    discount_amount: Money = None  # type: ignore[assignment]
    taxes: list[dict] = field(default_factory=list)
    fees: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("base_amount", "tax_amount", "fee_amount", "discount_amount"):
            if getattr(self, name) is None:
                setattr(self, name, Money.zero(self.currency))

    @property
    def total(self) -> Money:
        return self.base_amount + self.tax_amount + self.fee_amount - self.discount_amount

    def as_dict(self) -> dict:
        return {
            "base": self.base_amount.as_dict(),
            "taxes": self.tax_amount.as_dict(),
            "fees": self.fee_amount.as_dict(),
            "discount": self.discount_amount.as_dict(),
            "total": self.total.as_dict(),
            "tax_lines": self.taxes,
            "fee_lines": self.fees,
            "segments": [
                {
                    "flight_id": s.flight_id,
                    "cabin": s.cabin,
                    "rbd": s.rbd,
                    "fare_basis": s.fare_basis,
                    "fare_family_id": s.fare_family_id,
                    "base": s.base.as_dict(),
                }
                for s in self.segments
            ],
        }


class NoFareFound(Exception):
    pass


def passenger_type_for(dob: date | None, reference: date) -> str:
    """Age is evaluated at the return date, not the outbound date.

    A child who turns 12 mid-trip is priced as an adult for the whole journey — the industry
    rule, and the one that stops a passenger being refused boarding on the way home.
    """
    if dob is None:
        return PassengerType.ADULT

    years = reference.year - dob.year - ((reference.month, reference.day) < (dob.month, dob.day))
    if years < 2:
        return PassengerType.INFANT
    if years < 12:
        return PassengerType.CHILD
    return PassengerType.ADULT


def find_fare(
    flight: Flight,
    cabin: str,
    rbd: str,
    *,
    departure: date,
    return_date: date | None = None,
    passenger_type: str = PassengerType.ADULT,
) -> Fare | None:
    """Cheapest active fare whose rules the journey satisfies.

    Advance purchase and min/max stay are gates, not preferences: a fare the traveller does not
    qualify for must not be offered, because it will not be issuable at ticketing.
    """
    today = timezone.now().date()
    days_ahead = (departure - today).days

    candidates = Fare.objects.filter(
        airline_id=flight.airline_id,
        origin_airport_id=flight.origin_airport_id,
        destination_airport_id=flight.destination_airport_id,
        cabin=cabin,
        rbd=rbd,
        is_active=True,
        valid_from__lte=departure,
        valid_to__gte=departure,
        advance_purchase_days__lte=max(days_ahead, 0),
    ).filter(Q(passenger_type=passenger_type) | Q(passenger_type=PassengerType.ADULT))

    if return_date is not None:
        stay = (return_date - departure).days
        candidates = candidates.filter(
            Q(min_stay_days__isnull=True) | Q(min_stay_days__lte=stay)
        ).filter(Q(max_stay_days__isnull=True) | Q(max_stay_days__gte=stay))

    # Prefer a fare published for this exact passenger type over an adult fare we must discount.
    exact = candidates.filter(passenger_type=passenger_type).order_by("base_amount").first()
    return exact or candidates.order_by("base_amount").first()


def _pax_base(fare: Fare, passenger_type: str) -> Money:
    published = Money(Decimal(fare.base_amount), fare.currency)
    if fare.passenger_type == passenger_type:
        return published
    return published * DEFAULT_PAX_DISCOUNT[passenger_type]


def quote_itinerary(
    legs: list[tuple[Flight, str, str]],
    passengers: PassengerCount,
    *,
    currency: str = "USD",
    return_date: date | None = None,
    promo: PromoCode | None = None,
) -> PriceBreakdown:
    """Price a full itinerary for a party.

    ``legs`` is [(flight, cabin, rbd)] in travel order. Raises ``NoFareFound`` when any leg has
    no fare the journey qualifies for — an unpriceable itinerary must never surface as an offer.
    """
    breakdown = PriceBreakdown(currency=currency)
    base_total = Money.zero(currency)

    for flight, cabin, rbd in legs:
        departure = flight.departure_utc.date()
        adult_fare = find_fare(
            flight, cabin, rbd, departure=departure, return_date=return_date,
            passenger_type=PassengerType.ADULT,
        )
        if adult_fare is None:
            raise NoFareFound(
                f"No fare for {flight.designator} {cabin}/{rbd} on {departure}."
            )

        leg_total = Money.zero(currency)
        for passenger_type, count in passengers.as_types():
            if count == 0:
                continue
            fare = (
                find_fare(
                    flight, cabin, rbd, departure=departure, return_date=return_date,
                    passenger_type=passenger_type,
                )
                or adult_fare
            )
            leg_total = leg_total + (_pax_base(fare, passenger_type) * count)

        breakdown.segments.append(
            SegmentPrice(
                flight_id=flight.id,
                cabin=cabin,
                rbd=rbd,
                fare_id=adult_fare.id,
                fare_basis=adult_fare.fare_basis,
                fare_family_id=adult_fare.fare_family_id,
                base=leg_total,
            )
        )
        base_total = base_total + leg_total

    breakdown.base_amount = base_total
    breakdown.tax_amount, breakdown.taxes = _taxes(legs, passengers, base_total, currency)
    breakdown.fee_amount, breakdown.fees = _fees(legs, passengers, base_total, currency)
    breakdown.discount_amount = _discount(promo, base_total, currency)

    return breakdown


def _amount(rule, base: Money, currency: str) -> Money:
    if rule.calc_type == CalcType.PERCENT:
        return base * (Decimal(rule.value) / Decimal(100))
    return Money(Decimal(rule.value), rule.currency or currency)


def _taxes(
    legs: list[tuple[Flight, str, str]], passengers: PassengerCount, base: Money, currency: str
) -> tuple[Money, list[dict]]:
    airports = {leg[0].origin_airport_id for leg in legs} | {
        leg[0].destination_airport_id for leg in legs
    }
    countries = {leg[0].origin_airport.country_id for leg in legs} | {
        leg[0].destination_airport.country_id for leg in legs
    }

    rules = TaxRule.objects.filter(is_active=True).filter(
        Q(airport_id__in=airports) | Q(country_id__in=countries)
        | (Q(airport__isnull=True) & Q(country__isnull=True))
    )

    total = Money.zero(currency)
    lines: list[dict] = []

    for rule in rules:
        if rule.applies_to == TaxScope.ITINERARY:
            multiplier = passengers.total
        elif rule.applies_to == TaxScope.SEGMENT:
            multiplier = len(legs) * passengers.total
        elif rule.applies_to == TaxScope.DEPARTURE:
            multiplier = sum(
                1 for leg in legs if _matches(rule, leg[0].origin_airport_id,
                                              leg[0].origin_airport.country_id)
            ) * passengers.total
        else:
            multiplier = sum(
                1 for leg in legs if _matches(rule, leg[0].destination_airport_id,
                                              leg[0].destination_airport.country_id)
            ) * passengers.total

        if multiplier == 0:
            continue

        amount = _amount(rule, base, currency) * multiplier
        total = total + amount
        lines.append(
            {
                "code": rule.code,
                "name": rule.name,
                "amount": amount.as_dict(),
                "refundable": rule.is_refundable,
            }
        )

    return total, lines


def _matches(rule: TaxRule, airport_id: str, country_id: str) -> bool:
    if rule.airport_id:
        return rule.airport_id == airport_id
    if rule.country_id:
        return rule.country_id == country_id
    return True


def _fees(
    legs: list[tuple[Flight, str, str]], passengers: PassengerCount, base: Money, currency: str
) -> tuple[Money, list[dict]]:
    total = Money.zero(currency)
    lines: list[dict] = []

    for rule in FeeRule.objects.filter(is_active=True):
        if rule.scope == FeeScope.BOOKING:
            multiplier = 1
        elif rule.scope == FeeScope.PASSENGER:
            multiplier = passengers.total
        else:
            multiplier = len(legs) * passengers.total

        amount = _amount(rule, base, currency) * multiplier
        total = total + amount
        lines.append({"code": rule.code, "name": rule.name, "amount": amount.as_dict()})

    return total, lines


def _discount(promo: PromoCode | None, base: Money, currency: str) -> Money:
    if promo is None or not promo.is_active or promo.is_exhausted:
        return Money.zero(currency)

    now = timezone.now()
    if not (promo.valid_from <= now <= promo.valid_to):
        return Money.zero(currency)

    if promo.discount_type == DiscountType.PERCENT:
        return base * (Decimal(promo.value) / Decimal(100))
    return Money(Decimal(promo.value), promo.currency)
