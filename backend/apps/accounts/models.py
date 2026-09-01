from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.common.models import PublicIdModel, TimestampedModel

from .constants import AgencyStatus, DocumentType, Gender, RoleCode


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, PublicIdModel, TimestampedModel):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    locale = models.CharField(max_length=10, default="en")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    mfa_enabled = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        indexes = [models.Index(fields=["email"], name="idx_user_email")]

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email

    @property
    def role_codes(self) -> set[str]:
        return {assignment.role for assignment in self.role_assignments.all()}

    @property
    def agency_id_for_scope(self) -> int | None:
        assignment = self.role_assignments.filter(agency__isnull=False).first()
        return assignment.agency_id if assignment else None


class Agency(PublicIdModel, TimestampedModel):
    name = models.CharField(max_length=200)
    iata_code = models.CharField(max_length=8, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=16, choices=AgencyStatus.choices, default=AgencyStatus.ACTIVE
    )
    billing_address = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = "agencies"

    def __str__(self) -> str:
        return self.name

    @property
    def available_credit(self):
        return self.credit_limit - self.balance


class UserRole(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.CharField(max_length=20, choices=RoleCode.choices)
    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, null=True, blank=True, related_name="role_assignments"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "agency"], name="uniq_user_role_agency"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role}"


class AgencyMember(TimestampedModel):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agency_memberships")
    role = models.CharField(
        max_length=20, choices=RoleCode.choices, default=RoleCode.AGENCY_AGENT
    )
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agency", "user"], name="uniq_agency_member")
        ]


class Traveller(PublicIdModel, TimestampedModel):
    """A saved passenger profile. Document numbers are PII — see SPEC.md §12.4."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="travellers")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    nationality = models.CharField(max_length=2, blank=True)
    doc_type = models.CharField(max_length=20, choices=DocumentType.choices, blank=True)
    doc_number = models.CharField(max_length=64, blank=True)
    doc_expiry = models.DateField(null=True, blank=True)
    doc_issuing_country = models.CharField(max_length=2, blank=True)
    frequent_flyer_number = models.CharField(max_length=32, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["user", "last_name"], name="idx_traveller_user_name")]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"
