from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Agency, AgencyMember, Traveller, User, UserRole


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """See ``django.contrib.auth.admin.UserAdmin``; reworked for email-as-username."""

    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "mfa_enabled")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "locale")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "mfa_enabled",
                                    "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "iata_code", "status", "credit_limit", "balance")
    list_filter = ("status",)
    search_fields = ("name", "iata_code")


admin.site.register([UserRole, AgencyMember, Traveller])
