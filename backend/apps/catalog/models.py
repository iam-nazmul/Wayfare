from django.db import models

from apps.common.models import TimestampedModel


class Country(TimestampedModel):
    iso2 = models.CharField(max_length=2, primary_key=True)
    iso3 = models.CharField(max_length=3, blank=True)
    name = models.CharField(max_length=100)
    phone_prefix = models.CharField(max_length=8, blank=True)

    class Meta:
        verbose_name_plural = "countries"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class City(TimestampedModel):
    name = models.CharField(max_length=100)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="cities")
    timezone = models.CharField(max_length=64, help_text="IANA name, e.g. Asia/Dhaka")
    iata_code = models.CharField(max_length=3, blank=True, db_index=True)

    class Meta:
        verbose_name_plural = "cities"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Airport(TimestampedModel):
    #: Natural primary key: ``flight.origin_airport_id`` is the IATA code everywhere in the code.
    iata_code = models.CharField(max_length=3, primary_key=True)
    icao_code = models.CharField(max_length=4, blank=True)
    name = models.CharField(max_length=150)
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="airports")
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="airports")
    timezone = models.CharField(max_length=64, help_text="IANA name; schedules are authored here")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    #: Overrides the global domestic/international MCT for this airport.
    mct_domestic_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    mct_international_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["iata_code"]
        indexes = [
            models.Index(fields=["name"], name="idx_airport_name"),
            models.Index(fields=["is_active"], name="idx_airport_active"),
        ]

    def __str__(self) -> str:
        return f"{self.iata_code} — {self.name}"


class Airline(TimestampedModel):
    #: Natural primary key: ``flight.airline_id`` is the IATA code used to build the designator.
    iata_code = models.CharField(max_length=2, primary_key=True)
    icao_code = models.CharField(max_length=3, blank=True)
    name = models.CharField(max_length=150)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="airlines")
    logo_url = models.URLField(blank=True)
    #: 3-digit IATA ticketing prefix; the first three digits of every e-ticket number.
    ticketing_prefix = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["iata_code"]

    def __str__(self) -> str:
        return f"{self.iata_code} — {self.name}"


class Aircraft(TimestampedModel):
    iata_type_code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100, blank=True)
    total_seats_default = models.PositiveSmallIntegerField(default=180)

    class Meta:
        ordering = ["iata_type_code"]
        verbose_name_plural = "aircraft"

    def __str__(self) -> str:
        return f"{self.iata_type_code} — {self.name}"


class Currency(TimestampedModel):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=8, blank=True)
    minor_units = models.PositiveSmallIntegerField(default=2)

    class Meta:
        verbose_name_plural = "currencies"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class ExchangeRate(TimestampedModel):
    base = models.CharField(max_length=3)
    quote = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    valid_from = models.DateField()
    source = models.CharField(max_length=64, default="manual")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["base", "quote", "valid_from"], name="uniq_fx_base_quote_date"
            )
        ]
        indexes = [
            models.Index(fields=["base", "quote", "-valid_from"], name="idx_fx_lookup"),
        ]

    def __str__(self) -> str:
        return f"{self.base}/{self.quote} @ {self.rate}"
