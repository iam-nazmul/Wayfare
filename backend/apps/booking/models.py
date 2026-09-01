import uuid

from django.db import models

from apps.common.models import PublicIdModel, TimestampedModel
from apps.inventory.constants import Cabin
from apps.pricing.constants import TripType


class SearchQuery(PublicIdModel, TimestampedModel):
    """Thin record of an executed search. The rich analytics row goes to ClickHouse."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="searches",
    )
    session_id = models.CharField(max_length=64, blank=True)
    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    depart_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    trip_type = models.CharField(max_length=12, choices=TripType.choices)
    pax_adults = models.PositiveSmallIntegerField(default=1)
    pax_children = models.PositiveSmallIntegerField(default=0)
    pax_infants = models.PositiveSmallIntegerField(default=0)
    cabin = models.CharField(max_length=16, choices=Cabin.choices, default=Cabin.ECONOMY)
    currency = models.CharField(max_length=3, default="USD")
    results_count = models.PositiveSmallIntegerField(default=0)
    cache_hit = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(
                fields=["origin", "destination", "depart_date"], name="idx_search_market"
            ),
            models.Index(fields=["-created_at"], name="idx_search_recent"),
        ]
        verbose_name_plural = "search queries"

    def __str__(self) -> str:
        return f"{self.origin}-{self.destination} {self.depart_date}"


class Offer(TimestampedModel):
    """A priced, signed, time-limited search result.

    An offer holds no inventory. It is re-validated — signature, expiry and live availability —
    at booking time.
    """

    offer_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    search_query = models.ForeignKey(
        SearchQuery, on_delete=models.CASCADE, related_name="offers"
    )
    itinerary = models.JSONField(default=dict)
    price_breakdown = models.JSONField(default=dict)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    fare_family = models.ForeignKey(
        "pricing.FareFamily", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="offers",
    )
    seats_remaining = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    #: HMAC over the priced payload — a client cannot alter an offer before booking it.
    signature = models.CharField(max_length=64)

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"], name="idx_offer_expiry"),
            models.Index(fields=["search_query", "total_amount"], name="idx_offer_price"),
        ]
        ordering = ["total_amount"]

    def __str__(self) -> str:
        return f"{self.offer_id} {self.total_amount} {self.currency}"
