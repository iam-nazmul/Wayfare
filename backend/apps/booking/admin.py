from django.contrib import admin

from .models import Offer, SearchQuery


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
