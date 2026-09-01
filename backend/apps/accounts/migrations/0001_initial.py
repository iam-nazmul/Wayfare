import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.common.uuid7


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(blank=True, null=True, verbose_name="last login"),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates that this user has all permissions without "
                            "explicitly assigning them."
                        ),
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        default=apps.common.uuid7.uuid7, editable=False, unique=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("first_name", models.CharField(blank=True, max_length=100)),
                ("last_name", models.CharField(blank=True, max_length=100)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("locale", models.CharField(default="en", max_length=10)),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                ("mfa_enabled", models.BooleanField(default=False)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Agency",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        default=apps.common.uuid7.uuid7, editable=False, unique=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("iata_code", models.CharField(blank=True, max_length=8)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("credit_limit", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("SUSPENDED", "Suspended"),
                            ("CLOSED", "Closed"),
                        ],
                        default="ACTIVE",
                        max_length=16,
                    ),
                ),
                ("billing_address", models.JSONField(blank=True, default=dict)),
            ],
            options={"verbose_name_plural": "agencies"},
        ),
        migrations.CreateModel(
            name="Traveller",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        default=apps.common.uuid7.uuid7, editable=False, unique=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("first_name", models.CharField(max_length=100)),
                ("last_name", models.CharField(max_length=100)),
                ("dob", models.DateField(blank=True, null=True)),
                (
                    "gender",
                    models.CharField(
                        blank=True,
                        choices=[("M", "Male"), ("F", "Female"), ("X", "Unspecified")],
                        max_length=1,
                    ),
                ),
                ("nationality", models.CharField(blank=True, max_length=2)),
                (
                    "doc_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("PASSPORT", "Passport"),
                            ("NATIONAL_ID", "National ID"),
                            ("DRIVING_LICENCE", "Driving licence"),
                        ],
                        max_length=20,
                    ),
                ),
                ("doc_number", models.CharField(blank=True, max_length=64)),
                ("doc_expiry", models.DateField(blank=True, null=True)),
                ("doc_issuing_country", models.CharField(blank=True, max_length=2)),
                ("frequent_flyer_number", models.CharField(blank=True, max_length=32)),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="travellers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UserRole",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("TRAVELLER", "Traveller"),
                            ("AGENCY_AGENT", "Agency agent"),
                            ("AGENCY_ADMIN", "Agency admin"),
                            ("OPS_AGENT", "Ops agent"),
                            ("TICKETING", "Ticketing"),
                            ("FINANCE", "Finance"),
                            ("SUPERADMIN", "Superadmin"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "agency",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_assignments",
                        to="accounts.agency",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="AgencyMember",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("TRAVELLER", "Traveller"),
                            ("AGENCY_AGENT", "Agency agent"),
                            ("AGENCY_ADMIN", "Agency admin"),
                            ("OPS_AGENT", "Ops agent"),
                            ("TICKETING", "Ticketing"),
                            ("FINANCE", "Finance"),
                            ("SUPERADMIN", "Superadmin"),
                        ],
                        default="AGENCY_AGENT",
                        max_length=20,
                    ),
                ),
                ("commission_pct", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                (
                    "agency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="accounts.agency",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agency_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["email"], name="idx_user_email"),
        ),
        migrations.AddIndex(
            model_name="traveller",
            index=models.Index(fields=["user", "last_name"], name="idx_traveller_user_name"),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(
                fields=("user", "role", "agency"), name="uniq_user_role_agency"
            ),
        ),
        migrations.AddConstraint(
            model_name="agencymember",
            constraint=models.UniqueConstraint(fields=("agency", "user"), name="uniq_agency_member"),
        ),
    ]
