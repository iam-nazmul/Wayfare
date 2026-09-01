from decimal import Decimal

from django.db import models


class PassengerType(models.TextChoices):
    ADULT = "ADT", "Adult"
    CHILD = "CHD", "Child"
    INFANT = "INF", "Infant"


#: Fraction of the adult base fare charged per passenger type when no type-specific fare exists.
#: Infants travel on a lap and pay a token fare; they consume no seat inventory.
DEFAULT_PAX_DISCOUNT = {
    PassengerType.ADULT: Decimal("1.00"),
    PassengerType.CHILD: Decimal("0.75"),
    PassengerType.INFANT: Decimal("0.10"),
}

#: Age boundaries, evaluated at the *return* date of the journey.
CHILD_MIN_AGE = 2
ADULT_MIN_AGE = 12


class FareTier(models.TextChoices):
    BASIC = "BASIC", "Basic"
    STANDARD = "STANDARD", "Standard"
    FLEX = "FLEX", "Flex"


class CalcType(models.TextChoices):
    FIXED = "FIXED", "Fixed amount"
    PERCENT = "PERCENT", "Percentage of base fare"


class TaxScope(models.TextChoices):
    DEPARTURE = "DEPARTURE", "Per departure airport"
    ARRIVAL = "ARRIVAL", "Per arrival airport"
    ITINERARY = "ITINERARY", "Once per itinerary"
    SEGMENT = "SEGMENT", "Per segment"


class FeeScope(models.TextChoices):
    BOOKING = "BOOKING", "Per booking"
    PASSENGER = "PASSENGER", "Per passenger"
    SEGMENT = "SEGMENT", "Per segment"


class DiscountType(models.TextChoices):
    PERCENT = "PERCENT", "Percentage off base fare"
    FIXED = "FIXED", "Fixed amount off total"


class TripType(models.TextChoices):
    ONE_WAY = "ONE_WAY", "One way"
    ROUND_TRIP = "ROUND_TRIP", "Round trip"
    MULTI_CITY = "MULTI_CITY", "Multi city"
