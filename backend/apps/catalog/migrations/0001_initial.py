import django.db.models.deletion
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        # Airport typeahead ranks with similarity(); the extension must exist first.
        TrigramExtension(),
        migrations.CreateModel(
            name="Country",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("iso2", models.CharField(max_length=2, primary_key=True, serialize=False)),
                ("iso3", models.CharField(blank=True, max_length=3)),
                ("name", models.CharField(max_length=100)),
                ("phone_prefix", models.CharField(blank=True, max_length=8)),
            ],
            options={"verbose_name_plural": "countries", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Aircraft",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("iata_type_code", models.CharField(max_length=3, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("manufacturer", models.CharField(blank=True, max_length=100)),
                ("total_seats_default", models.PositiveSmallIntegerField(default=180)),
            ],
            options={"verbose_name_plural": "aircraft", "ordering": ["iata_type_code"]},
        ),
        migrations.CreateModel(
            name="Currency",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=3, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=64)),
                ("symbol", models.CharField(blank=True, max_length=8)),
                ("minor_units", models.PositiveSmallIntegerField(default=2)),
            ],
            options={"verbose_name_plural": "currencies", "ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="ExchangeRate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("base", models.CharField(max_length=3)),
                ("quote", models.CharField(max_length=3)),
                ("rate", models.DecimalField(decimal_places=8, max_digits=18)),
                ("valid_from", models.DateField()),
                ("source", models.CharField(default="manual", max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name="City",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "timezone",
                    models.CharField(help_text="IANA name, e.g. Asia/Dhaka", max_length=64),
                ),
                ("iata_code", models.CharField(blank=True, db_index=True, max_length=3)),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cities",
                        to="catalog.country",
                    ),
                ),
            ],
            options={"verbose_name_plural": "cities", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Airline",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "iata_code",
                    models.CharField(max_length=2, primary_key=True, serialize=False),
                ),
                ("icao_code", models.CharField(blank=True, max_length=3)),
                ("name", models.CharField(max_length=150)),
                ("logo_url", models.URLField(blank=True)),
                ("ticketing_prefix", models.CharField(max_length=3)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="airlines",
                        to="catalog.country",
                    ),
                ),
            ],
            options={"ordering": ["iata_code"]},
        ),
        migrations.CreateModel(
            name="Airport",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "iata_code",
                    models.CharField(max_length=3, primary_key=True, serialize=False),
                ),
                ("icao_code", models.CharField(blank=True, max_length=4)),
                ("name", models.CharField(max_length=150)),
                (
                    "timezone",
                    models.CharField(
                        help_text="IANA name; schedules are authored here", max_length=64
                    ),
                ),
                (
                    "latitude",
                    models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
                ),
                (
                    "longitude",
                    models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
                ),
                ("mct_domestic_minutes", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "mct_international_minutes",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "city",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="airports",
                        to="catalog.city",
                    ),
                ),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="airports",
                        to="catalog.country",
                    ),
                ),
            ],
            options={"ordering": ["iata_code"]},
        ),
        migrations.AddIndex(
            model_name="airport",
            index=models.Index(fields=["name"], name="idx_airport_name"),
        ),
        migrations.AddIndex(
            model_name="airport",
            index=models.Index(fields=["is_active"], name="idx_airport_active"),
        ),
        migrations.AddIndex(
            model_name="exchangerate",
            index=models.Index(fields=["base", "quote", "-valid_from"], name="idx_fx_lookup"),
        ),
        migrations.AddConstraint(
            model_name="exchangerate",
            constraint=models.UniqueConstraint(
                fields=("base", "quote", "valid_from"), name="uniq_fx_base_quote_date"
            ),
        ),
    ]
