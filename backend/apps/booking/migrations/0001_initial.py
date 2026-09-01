import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.common.uuid7

CABIN_CHOICES = [
    ("ECONOMY", "Economy"),
    ("PREMIUM_ECONOMY", "Premium economy"),
    ("BUSINESS", "Business"),
    ("FIRST", "First"),
]

TRIP_CHOICES = [
    ("ONE_WAY", "One way"),
    ("ROUND_TRIP", "Round trip"),
    ("MULTI_CITY", "Multi city"),
]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("pricing", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchQuery",
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
                ("session_id", models.CharField(blank=True, max_length=64)),
                ("origin", models.CharField(max_length=3)),
                ("destination", models.CharField(max_length=3)),
                ("depart_date", models.DateField()),
                ("return_date", models.DateField(blank=True, null=True)),
                ("trip_type", models.CharField(choices=TRIP_CHOICES, max_length=12)),
                ("pax_adults", models.PositiveSmallIntegerField(default=1)),
                ("pax_children", models.PositiveSmallIntegerField(default=0)),
                ("pax_infants", models.PositiveSmallIntegerField(default=0)),
                (
                    "cabin",
                    models.CharField(choices=CABIN_CHOICES, default="ECONOMY", max_length=16),
                ),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("results_count", models.PositiveSmallIntegerField(default=0)),
                ("cache_hit", models.BooleanField(default=False)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="searches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"verbose_name_plural": "search queries"},
        ),
        migrations.CreateModel(
            name="Offer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("offer_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("itinerary", models.JSONField(default=dict)),
                ("price_breakdown", models.JSONField(default=dict)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("seats_remaining", models.PositiveSmallIntegerField(default=0)),
                ("expires_at", models.DateTimeField()),
                ("signature", models.CharField(max_length=64)),
                (
                    "fare_family",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="offers",
                        to="pricing.farefamily",
                    ),
                ),
                (
                    "search_query",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offers",
                        to="booking.searchquery",
                    ),
                ),
            ],
            options={"ordering": ["total_amount"]},
        ),
        migrations.AddIndex(
            model_name="searchquery",
            index=models.Index(
                fields=["origin", "destination", "depart_date"], name="idx_search_market"
            ),
        ),
        migrations.AddIndex(
            model_name="searchquery",
            index=models.Index(fields=["-created_at"], name="idx_search_recent"),
        ),
        migrations.AddIndex(
            model_name="offer",
            index=models.Index(fields=["expires_at"], name="idx_offer_expiry"),
        ),
        migrations.AddIndex(
            model_name="offer",
            index=models.Index(
                fields=["search_query", "total_amount"], name="idx_offer_price"
            ),
        ),
    ]
