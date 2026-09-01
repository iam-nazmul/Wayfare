import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q

CABIN_CHOICES = [
    ("ECONOMY", "Economy"),
    ("PREMIUM_ECONOMY", "Premium economy"),
    ("BUSINESS", "Business"),
    ("FIRST", "First"),
]

PAX_CHOICES = [("ADT", "Adult"), ("CHD", "Child"), ("INF", "Infant")]
CALC_CHOICES = [("FIXED", "Fixed amount"), ("PERCENT", "Percentage of base fare")]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FareFamily",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=16)),
                ("name", models.CharField(max_length=64)),
                ("cabin", models.CharField(choices=CABIN_CHOICES, max_length=16)),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("BASIC", "Basic"),
                            ("STANDARD", "Standard"),
                            ("FLEX", "Flex"),
                        ],
                        default="STANDARD",
                        max_length=12,
                    ),
                ),
                ("includes", models.JSONField(blank=True, default=dict)),
                ("changeable", models.BooleanField(default=False)),
                ("change_fee", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("refundable", models.BooleanField(default=False)),
                ("refund_fee", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("allows_residual_value", models.BooleanField(default=False)),
                (
                    "baggage_allowance",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='{"cabin_kg": 7, "checked_kg": 23, "pieces": 1}',
                    ),
                ),
                ("seat_selection_free", models.BooleanField(default=False)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "airline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fare_families",
                        to="catalog.airline",
                    ),
                ),
            ],
            options={"verbose_name_plural": "fare families", "ordering": ["sort_order"]},
        ),
        migrations.CreateModel(
            name="Fare",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cabin", models.CharField(choices=CABIN_CHOICES, max_length=16)),
                ("rbd", models.CharField(max_length=1)),
                ("fare_basis", models.CharField(max_length=16)),
                ("base_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "passenger_type",
                    models.CharField(choices=PAX_CHOICES, default="ADT", max_length=3),
                ),
                ("min_stay_days", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("max_stay_days", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("advance_purchase_days", models.PositiveSmallIntegerField(default=0)),
                ("valid_from", models.DateField()),
                ("valid_to", models.DateField()),
                ("is_active", models.BooleanField(default=True)),
                (
                    "airline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fares",
                        to="catalog.airline",
                    ),
                ),
                (
                    "destination_airport",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fares_in",
                        to="catalog.airport",
                    ),
                ),
                (
                    "origin_airport",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fares_out",
                        to="catalog.airport",
                    ),
                ),
                (
                    "fare_family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fares",
                        to="pricing.farefamily",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="TaxRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=8)),
                ("name", models.CharField(max_length=100)),
                (
                    "applies_to",
                    models.CharField(
                        choices=[
                            ("DEPARTURE", "Per departure airport"),
                            ("ARRIVAL", "Per arrival airport"),
                            ("ITINERARY", "Once per itinerary"),
                            ("SEGMENT", "Per segment"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "calc_type",
                    models.CharField(choices=CALC_CHOICES, default="FIXED", max_length=8),
                ),
                ("value", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("is_refundable", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "airport",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="taxes",
                        to="catalog.airport",
                    ),
                ),
                (
                    "country",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="taxes",
                        to="catalog.country",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="FeeRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=8, unique=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("BOOKING", "Per booking"),
                            ("PASSENGER", "Per passenger"),
                            ("SEGMENT", "Per segment"),
                        ],
                        default="BOOKING",
                        max_length=12,
                    ),
                ),
                (
                    "calc_type",
                    models.CharField(choices=CALC_CHOICES, default="FIXED", max_length=8),
                ),
                ("value", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="PromoCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=24, unique=True)),
                (
                    "discount_type",
                    models.CharField(
                        choices=[
                            ("PERCENT", "Percentage off base fare"),
                            ("FIXED", "Fixed amount off total"),
                        ],
                        default="PERCENT",
                        max_length=8,
                    ),
                ),
                ("value", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "max_uses",
                    models.PositiveIntegerField(default=0, help_text="0 means unlimited"),
                ),
                ("uses", models.PositiveIntegerField(default=0)),
                ("per_user_limit", models.PositiveSmallIntegerField(default=1)),
                ("valid_from", models.DateTimeField()),
                ("valid_to", models.DateTimeField()),
                ("conditions", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="PromoRedemption",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("booking_pnr", models.CharField(blank=True, max_length=6)),
                (
                    "promo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="redemptions",
                        to="pricing.promocode",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="promo_redemptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.AddIndex(
            model_name="fare",
            index=models.Index(
                fields=["origin_airport", "destination_airport", "cabin",
                        "valid_from", "valid_to"],
                name="idx_fare_market",
            ),
        ),
        migrations.AddIndex(
            model_name="fare",
            index=models.Index(fields=["airline", "rbd"], name="idx_fare_rbd"),
        ),
        migrations.AddIndex(
            model_name="taxrule",
            index=models.Index(fields=["is_active", "applies_to"], name="idx_tax_active"),
        ),
        migrations.AddIndex(
            model_name="promoredemption",
            index=models.Index(fields=["promo", "user"], name="idx_promo_user"),
        ),
        migrations.AddConstraint(
            model_name="farefamily",
            constraint=models.UniqueConstraint(
                fields=("airline", "code"), name="uniq_fare_family_code"
            ),
        ),
        migrations.AddConstraint(
            model_name="fare",
            constraint=models.CheckConstraint(
                condition=Q(valid_to__gte=F("valid_from")), name="fare_validity_range"
            ),
        ),
        migrations.AddConstraint(
            model_name="fare",
            constraint=models.CheckConstraint(
                condition=Q(base_amount__gte=0), name="fare_amount_non_negative"
            ),
        ),
        migrations.AddConstraint(
            model_name="taxrule",
            constraint=models.UniqueConstraint(
                fields=("code", "country", "airport"), name="uniq_tax_rule_scope"
            ),
        ),
        migrations.AddConstraint(
            model_name="promocode",
            constraint=models.CheckConstraint(
                condition=Q(max_uses=0) | Q(uses__lte=F("max_uses")),
                name="promo_within_max_uses",
            ),
        ),
    ]
