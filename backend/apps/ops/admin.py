from django.contrib import admin

from .models import AuditLog, Disruption, OutboxEvent, RebookOption


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "aggregate_type", "aggregate_id", "available_at", "processed_at")
    list_filter = ("event_type", "aggregate_type")
    search_fields = ("aggregate_id",)
    readonly_fields = ("payload",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "object_type", "object_id", "actor", "created_at")
    list_filter = ("action", "object_type")
    search_fields = ("object_id",)
    readonly_fields = ("before", "after")


class RebookOptionInline(admin.TabularInline):
    model = RebookOption
    extra = 0


@admin.register(Disruption)
class DisruptionAdmin(admin.ModelAdmin):
    list_display = ("flight", "type", "delay_minutes", "detected_at", "resolved_at")
    list_filter = ("type",)
    search_fields = ("flight__flight_number",)
    inlines = [RebookOptionInline]


@admin.register(RebookOption)
class RebookOptionAdmin(admin.ModelAdmin):
    list_display = ("booking", "proposed_flight", "cabin", "rbd", "status", "expires_at")
    list_filter = ("status", "cabin")
    search_fields = ("booking__pnr",)
