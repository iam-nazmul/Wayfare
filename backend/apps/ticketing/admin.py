from django.contrib import admin

from .models import Ticket, TicketCoupon, TicketEvent, TicketSerial


class TicketCouponInline(admin.TabularInline):
    model = TicketCoupon
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "booking", "passenger", "status", "total_amount",
                    "currency", "issued_at")
    list_filter = ("status", "issuing_airline")
    search_fields = ("ticket_number", "booking__pnr")
    inlines = [TicketCouponInline]


@admin.register(TicketEvent)
class TicketEventAdmin(admin.ModelAdmin):
    list_display = ("ticket", "event_type", "actor", "created_at")
    list_filter = ("event_type",)


@admin.register(TicketSerial)
class TicketSerialAdmin(admin.ModelAdmin):
    list_display = ("airline_prefix", "last_serial")
