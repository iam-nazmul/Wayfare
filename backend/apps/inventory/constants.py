from django.db import models


class Cabin(models.TextChoices):
    ECONOMY = "ECONOMY", "Economy"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY", "Premium economy"
    BUSINESS = "BUSINESS", "Business"
    FIRST = "FIRST", "First"


#: Cheapest first. Upsell and downgrade logic walks this order.
CABIN_ORDER = [Cabin.ECONOMY, Cabin.PREMIUM_ECONOMY, Cabin.BUSINESS, Cabin.FIRST]


class FlightStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    DELAYED = "DELAYED", "Delayed"
    BOARDING = "BOARDING", "Boarding"
    DEPARTED = "DEPARTED", "Departed"
    ARRIVED = "ARRIVED", "Arrived"
    CANCELLED = "CANCELLED", "Cancelled"
    DIVERTED = "DIVERTED", "Diverted"


#: Statuses that can still be sold.
SELLABLE_FLIGHT_STATUSES = frozenset({FlightStatus.SCHEDULED, FlightStatus.DELAYED})


class ScheduleStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    RETIRED = "RETIRED", "Retired"


class SeatStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    HELD = "HELD", "Held"
    ASSIGNED = "ASSIGNED", "Assigned"
    BLOCKED = "BLOCKED", "Blocked"


class SeatCharacteristic(models.TextChoices):
    WINDOW = "WINDOW", "Window"
    AISLE = "AISLE", "Aisle"
    MIDDLE = "MIDDLE", "Middle"
    EXTRA_LEGROOM = "EXTRA_LEGROOM", "Extra legroom"
    NO_RECLINE = "NO_RECLINE", "Does not recline"
    BASSINET = "BASSINET", "Bassinet position"


#: Single-letter inventory buckets, most expensive first within a cabin.
DEFAULT_RBDS = {
    Cabin.ECONOMY: ["Y", "B", "M", "H", "Q", "V", "L"],
    Cabin.PREMIUM_ECONOMY: ["W", "S"],
    Cabin.BUSINESS: ["J", "C", "D"],
    Cabin.FIRST: ["F", "A"],
}
