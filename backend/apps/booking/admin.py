from django.contrib import admin

from .models import (
    Booking,
    BookingSegment,
    InventoryHold,
    Offer,
    Passenger,
    SearchQuery,
)


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ("origin", "destination", "depart_date", "cabin",
                    "results_count", "cache_hit", "latency_ms", "created_at")
    list_filter = ("cabin", "trip_type", "cache_hit")
    search_fields = ("origin", "destination")
    date_hierarchy = "created_at"


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("offer_id", "total_amount", "currency", "seats_remaining", "expires_at")
    readonly_fields = ("offer_id", "signature", "itinerary", "price_breakdown")


class BookingSegmentInline(admin.TabularInline):
    model = BookingSegment
    extra = 0


class PassengerInline(admin.TabularInline):
    model = Passenger
    extra = 0
    fk_name = "booking"


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("pnr", "status", "total_amount", "currency", "contact_email",
                    "hold_expires_at", "created_at")
    list_filter = ("status", "trip_type", "source_channel")
    search_fields = ("pnr", "contact_email")
    date_hierarchy = "created_at"
    inlines = [BookingSegmentInline, PassengerInline]
    #: Status moves through services/state.py::transition, never by hand in the admin.
    readonly_fields = ("pnr", "status", "version")


@admin.register(InventoryHold)
class InventoryHoldAdmin(admin.ModelAdmin):
    list_display = ("booking", "flight", "cabin", "rbd", "seats", "expires_at", "released_at")
    list_filter = ("cabin", "rbd")
