from django.contrib import admin

from .models import Aircraft, Airline, Airport, City, Country, Currency, ExchangeRate


@admin.register(Airport)
class AirportAdmin(admin.ModelAdmin):
    list_display = ("iata_code", "name", "city", "country", "timezone", "is_active")
    list_filter = ("is_active", "country")
    search_fields = ("iata_code", "icao_code", "name", "city__name")
    autocomplete_fields = ("city", "country")


@admin.register(Airline)
class AirlineAdmin(admin.ModelAdmin):
    list_display = ("iata_code", "name", "ticketing_prefix", "is_active")
    list_filter = ("is_active",)
    search_fields = ("iata_code", "name")


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "timezone", "iata_code")
    search_fields = ("name", "iata_code")


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("iso2", "iso3", "name")
    search_fields = ("iso2", "name")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("base", "quote", "rate", "valid_from", "source")
    list_filter = ("base", "quote")


admin.site.register([Aircraft, Currency])
