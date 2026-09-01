from django.db import models
from django.db.models import F, Q

from apps.common.models import TimestampedModel
from apps.inventory.constants import Cabin

from .constants import (
    CalcType,
    DiscountType,
    FareTier,
    FeeScope,
    PassengerType,
    TaxScope,
)


class FareFamily(TimestampedModel):
    """Marketed bundle: what the passenger may change, refund, and carry."""

    airline = models.ForeignKey(
        "catalog.Airline", on_delete=models.CASCADE, related_name="fare_families"
    )
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=64)
    cabin = models.CharField(max_length=16, choices=Cabin.choices)
    tier = models.CharField(max_length=12, choices=FareTier.choices, default=FareTier.STANDARD)
    includes = models.JSONField(default=dict, blank=True)

    changeable = models.BooleanField(default=False)
    change_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refundable = models.BooleanField(default=False)
    refund_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    #: True when an exchange to a cheaper fare leaves usable credit.
    allows_residual_value = models.BooleanField(default=False)

    baggage_allowance = models.JSONField(
        default=dict, blank=True, help_text='{"cabin_kg": 7, "checked_kg": 23, "pieces": 1}'
    )
    seat_selection_free = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["airline", "code"], name="uniq_fare_family_code")
        ]
        ordering = ["sort_order"]
        verbose_name_plural = "fare families"

    def __str__(self) -> str:
        return f"{self.airline_id} {self.name}"


class Fare(TimestampedModel):
    """A published fare for one market, cabin and booking class."""

    airline = models.ForeignKey("catalog.Airline", on_delete=models.CASCADE, related_name="fares")
    origin_airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.CASCADE, related_name="fares_out"
    )
    destination_airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.CASCADE, related_name="fares_in"
    )
    cabin = models.CharField(max_length=16, choices=Cabin.choices)
    rbd = models.CharField(max_length=1)
    fare_family = models.ForeignKey(FareFamily, on_delete=models.PROTECT, related_name="fares")
    fare_basis = models.CharField(max_length=16)

    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    passenger_type = models.CharField(
        max_length=3, choices=PassengerType.choices, default=PassengerType.ADULT
    )

    min_stay_days = models.PositiveSmallIntegerField(null=True, blank=True)
    max_stay_days = models.PositiveSmallIntegerField(null=True, blank=True)
    advance_purchase_days = models.PositiveSmallIntegerField(default=0)

    valid_from = models.DateField()
    valid_to = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["origin_airport", "destination_airport", "cabin", "valid_from", "valid_to"],
                name="idx_fare_market",
            ),
            models.Index(fields=["airline", "rbd"], name="idx_fare_rbd"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__gte=F("valid_from")), name="fare_validity_range"
            ),
            models.CheckConstraint(condition=Q(base_amount__gte=0), name="fare_amount_non_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.fare_basis} {self.base_amount} {self.currency}"


class TaxRule(TimestampedModel):
    """Government and airport taxes. Most are non-refundable even on a refundable fare."""

    code = models.CharField(max_length=8)
    name = models.CharField(max_length=100)
    country = models.ForeignKey(
        "catalog.Country", on_delete=models.CASCADE, null=True, blank=True, related_name="taxes"
    )
    airport = models.ForeignKey(
        "catalog.Airport", on_delete=models.CASCADE, null=True, blank=True, related_name="taxes"
    )
    applies_to = models.CharField(max_length=12, choices=TaxScope.choices)
    calc_type = models.CharField(max_length=8, choices=CalcType.choices, default=CalcType.FIXED)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    is_refundable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code", "country", "airport"], name="uniq_tax_rule_scope"
            )
        ]
        indexes = [models.Index(fields=["is_active", "applies_to"], name="idx_tax_active")]

    def __str__(self) -> str:
        return f"{self.code} {self.value}"


class FeeRule(TimestampedModel):
    """Carrier fees: booking, service, payment surcharges."""

    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=12, choices=FeeScope.choices, default=FeeScope.BOOKING)
    calc_type = models.CharField(max_length=8, choices=CalcType.choices, default=CalcType.FIXED)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.code} {self.value}"


class PromoCode(TimestampedModel):
    code = models.CharField(max_length=24, unique=True)
    discount_type = models.CharField(
        max_length=8, choices=DiscountType.choices, default=DiscountType.PERCENT
    )
    value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    max_uses = models.PositiveIntegerField(default=0, help_text="0 means unlimited")
    uses = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveSmallIntegerField(default=1)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    conditions = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(max_uses=0) | Q(uses__lte=F("max_uses")), name="promo_within_max_uses"
            )
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def is_exhausted(self) -> bool:
        return self.max_uses > 0 and self.uses >= self.max_uses


class PromoRedemption(TimestampedModel):
    promo = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="promo_redemptions",
    )
    booking_pnr = models.CharField(max_length=6, blank=True)

    class Meta:
        indexes = [models.Index(fields=["promo", "user"], name="idx_promo_user")]
