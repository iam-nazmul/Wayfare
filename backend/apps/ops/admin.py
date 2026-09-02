from django.contrib import admin

from .models import AuditLog, OutboxEvent


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
