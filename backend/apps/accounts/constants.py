from django.db import models


class RoleCode(models.TextChoices):
    TRAVELLER = "TRAVELLER", "Traveller"
    AGENCY_AGENT = "AGENCY_AGENT", "Agency agent"
    AGENCY_ADMIN = "AGENCY_ADMIN", "Agency admin"
    OPS_AGENT = "OPS_AGENT", "Ops agent"
    TICKETING = "TICKETING", "Ticketing"
    FINANCE = "FINANCE", "Finance"
    SUPERADMIN = "SUPERADMIN", "Superadmin"


STAFF_ROLES = frozenset(
    {RoleCode.OPS_AGENT, RoleCode.TICKETING, RoleCode.FINANCE, RoleCode.SUPERADMIN}
)

#: Roles that must carry a second factor — see SPEC.md §12.1.
MFA_REQUIRED_ROLES = STAFF_ROLES


class AgencyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    CLOSED = "CLOSED", "Closed"


class DocumentType(models.TextChoices):
    PASSPORT = "PASSPORT", "Passport"
    NATIONAL_ID = "NATIONAL_ID", "National ID"
    DRIVING_LICENCE = "DRIVING_LICENCE", "Driving licence"


class Gender(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"
    UNSPECIFIED = "X", "Unspecified"
