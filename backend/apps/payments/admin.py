from django.contrib import admin

from .models import LedgerEntry, Payment, PaymentIntent, ProviderWebhookEvent, Refund


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("provider_intent_id", "booking", "amount", "currency", "status", "expires_at")
    list_filter = ("provider", "status")
    search_fields = ("provider_intent_id", "booking__pnr")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("provider_charge_id", "booking", "amount", "currency", "status",
                    "card_brand", "card_last4", "captured_at")
    list_filter = ("provider", "status", "card_brand")
    search_fields = ("provider_charge_id", "booking__pnr")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("booking", "amount", "currency", "status", "requested_by", "processed_at")
    list_filter = ("status",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("booking", "entry_type", "debit", "credit", "balance_after", "created_at")
    list_filter = ("entry_type",)
    #: Append-only: the ledger is evidence, not a working document.
    readonly_fields = tuple(field.name for field in LedgerEntry._meta.fields)

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ProviderWebhookEvent)
class ProviderWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider_event_id", "provider", "event_type", "signature_verified",
                    "processed_at", "attempts")
    list_filter = ("provider", "event_type", "signature_verified")
    readonly_fields = ("payload",)
