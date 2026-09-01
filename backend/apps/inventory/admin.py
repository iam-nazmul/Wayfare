from django.contrib import admin

from .models import (
    BookingClass,
    CabinConfig,
    Flight,
    FlightSchedule,
    Route,
    Seat,
    SeatMapTemplate,
)


class CabinConfigInline(admin.TabularInline):
    model = CabinConfig
    extra = 0
    readonly_fields = ("seats_sold", "seats_held")


class BookingClassInline(admin.TabularInline):
    model = BookingClass
    extra = 0
    readonly_fields = ("sold", "held")


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ("designator", "origin_airport", "destination_airport",
                    "departure_utc", "status")
    list_filter = ("status", "airline")
    search_fields = ("flight_number", "origin_airport__iata_code",
                     "destination_airport__iata_code")
    date_hierarchy = "departure_utc"
    inlines = [CabinConfigInline, BookingClassInline]
    readonly_fields = ("public_id", "version")


@admin.register(FlightSchedule)
class FlightScheduleAdmin(admin.ModelAdmin):
    list_display = ("airline", "flight_number", "route", "dep_time_local",
                    "effective_from", "effective_to", "status")
    list_filter = ("status", "airline")


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("flight", "seat_number", "cabin", "status", "is_exit_row")
    list_filter = ("cabin", "status", "is_exit_row")
    search_fields = ("seat_number",)


admin.site.register([Route, SeatMapTemplate])
