import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q

import apps.common.uuid7


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SeatMapTemplate",
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
                ("layout", models.JSONField(default=dict)),
                (
                    "aircraft",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="seat_maps",
                        to="catalog.aircraft",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Route",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "airline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="routes",
                        to="catalog.airline",
                    ),
                ),
                (
                    "destination_airport",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="routes_in",
                        to="catalog.airport",
                    ),
                ),
                (
                    "origin_airport",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="routes_out",
                        to="catalog.airport",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="FlightSchedule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("flight_number", models.CharField(max_length=5)),
                ("dep_time_local", models.TimeField()),
                ("arr_time_local", models.TimeField()),
                ("arrival_day_offset", models.PositiveSmallIntegerField(default=0)),
                (
                    "days_of_week",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.BooleanField(), default=list, size=7
                    ),
                ),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("SUSPENDED", "Suspended"),
                            ("RETIRED", "Retired"),
                        ],
                        default="ACTIVE",
                        max_length=12,
                    ),
                ),
                (
                    "default_cabin_capacity",
                    models.JSONField(default=dict, help_text='{"ECONOMY": 162, "BUSINESS": 18}'),
                ),
                (
                    "aircraft",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="schedules",
                        to="catalog.aircraft",
                    ),
                ),
                (
                    "airline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedules",
                        to="catalog.airline",
                    ),
                ),
                (
                    "route",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedules",
                        to="inventory.route",
                    ),
                ),
                (
                    "seat_map_template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="schedules",
                        to="inventory.seatmaptemplate",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Flight",
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
                ("flight_number", models.CharField(max_length=5)),
                ("departure_utc", models.DateTimeField()),
                ("arrival_utc", models.DateTimeField()),
                ("departure_local", models.DateTimeField()),
                ("arrival_local", models.DateTimeField()),
                ("duration_minutes", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SCHEDULED", "Scheduled"),
                            ("DELAYED", "Delayed"),
                            ("BOARDING", "Boarding"),
                            ("DEPARTED", "Departed"),
                            ("ARRIVED", "Arrived"),
                            ("CANCELLED", "Cancelled"),
                            ("DIVERTED", "Diverted"),
                        ],
                        default="SCHEDULED",
                        max_length=12,
                    ),
                ),
                ("gate", models.CharField(blank=True, max_length=8)),
                ("terminal", models.CharField(blank=True, max_length=8)),
                ("actual_departure_utc", models.DateTimeField(blank=True, null=True)),
                ("delay_minutes", models.IntegerField(default=0)),
                ("version", models.PositiveIntegerField(default=0)),
                (
                    "aircraft",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="flights",
                        to="catalog.aircraft",
                    ),
                ),
                (
                    "airline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="flights",
                        to="catalog.airline",
                    ),
                ),
                (
                    "destination_airport",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="arrivals",
                        to="catalog.airport",
                    ),
                ),
                (
                    "origin_airport",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="departures",
                        to="catalog.airport",
                    ),
                ),
                (
                    "schedule",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="flights",
                        to="inventory.flightschedule",
                    ),
                ),
                (
                    "seat_map_template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="flights",
                        to="inventory.seatmaptemplate",
                    ),
                ),
            ],
            options={"ordering": ["departure_utc"]},
        ),
        migrations.CreateModel(
            name="CabinConfig",
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
                    "cabin",
                    models.CharField(
                        choices=[
                            ("ECONOMY", "Economy"),
                            ("PREMIUM_ECONOMY", "Premium economy"),
                            ("BUSINESS", "Business"),
                            ("FIRST", "First"),
                        ],
                        max_length=16,
                    ),
                ),
                ("capacity", models.PositiveSmallIntegerField()),
                ("seats_sold", models.PositiveSmallIntegerField(default=0)),
                ("seats_held", models.PositiveSmallIntegerField(default=0)),
                ("oversell_allowance", models.PositiveSmallIntegerField(default=0)),
                (
                    "flight",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cabins",
                        to="inventory.flight",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="BookingClass",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rbd", models.CharField(max_length=1)),
                ("authorised", models.PositiveSmallIntegerField(default=0)),
                ("sold", models.PositiveSmallIntegerField(default=0)),
                ("held", models.PositiveSmallIntegerField(default=0)),
                ("is_open", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "cabin_config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="booking_classes",
                        to="inventory.cabinconfig",
                    ),
                ),
                (
                    "flight",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="booking_classes",
                        to="inventory.flight",
                    ),
                ),
            ],
            options={"ordering": ["sort_order"]},
        ),
        migrations.CreateModel(
            name="Seat",
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
                    "cabin",
                    models.CharField(
                        choices=[
                            ("ECONOMY", "Economy"),
                            ("PREMIUM_ECONOMY", "Premium economy"),
                            ("BUSINESS", "Business"),
                            ("FIRST", "First"),
                        ],
                        max_length=16,
                    ),
                ),
                ("row", models.PositiveSmallIntegerField()),
                ("column", models.CharField(max_length=1)),
                ("seat_number", models.CharField(max_length=4)),
                (
                    "characteristics",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=20), blank=True, default=list,
                        size=None,
                    ),
                ),
                ("is_exit_row", models.BooleanField(default=False)),
                ("is_blocked", models.BooleanField(default=False)),
                ("seat_fee_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("seat_fee_currency", models.CharField(default="USD", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("AVAILABLE", "Available"),
                            ("HELD", "Held"),
                            ("ASSIGNED", "Assigned"),
                            ("BLOCKED", "Blocked"),
                        ],
                        default="AVAILABLE",
                        max_length=12,
                    ),
                ),
                (
                    "flight",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seats",
                        to="inventory.flight",
                    ),
                ),
            ],
            options={"ordering": ["row", "column"]},
        ),
        migrations.CreateModel(
            name="ScheduleMaterialisation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("window_start", models.DateField()),
                ("window_end", models.DateField()),
                ("flights_created", models.PositiveIntegerField(default=0)),
                ("flights_skipped", models.PositiveIntegerField(default=0)),
                (
                    "schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="materialisations",
                        to="inventory.flightschedule",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.AddIndex(
            model_name="flightschedule",
            index=models.Index(fields=["airline", "flight_number"], name="idx_schedule_flightno"),
        ),
        migrations.AddIndex(
            model_name="flightschedule",
            index=models.Index(fields=["status", "effective_to"], name="idx_schedule_active"),
        ),
        migrations.AddIndex(
            model_name="flight",
            index=models.Index(
                fields=["origin_airport", "destination_airport", "departure_utc"],
                name="idx_flight_od_date",
            ),
        ),
        migrations.AddIndex(
            model_name="flight",
            index=models.Index(
                condition=Q(status__in=["SCHEDULED", "DELAYED"]),
                fields=["departure_utc"],
                name="idx_flight_sellable",
            ),
        ),
        migrations.AddIndex(
            model_name="flight",
            index=models.Index(fields=["schedule", "departure_utc"], name="idx_flight_schedule"),
        ),
        migrations.AddIndex(
            model_name="bookingclass",
            index=models.Index(fields=["flight", "sort_order"], name="idx_rbd_ladder"),
        ),
        migrations.AddIndex(
            model_name="seat",
            index=models.Index(fields=["flight", "cabin", "status"], name="idx_seat_availability"),
        ),
        migrations.AddIndex(
            model_name="schedulematerialisation",
            index=models.Index(
                fields=["schedule", "-window_end"], name="idx_materialisation_window"
            ),
        ),
        migrations.AddConstraint(
            model_name="route",
            constraint=models.UniqueConstraint(
                fields=("airline", "origin_airport", "destination_airport"), name="uniq_route"
            ),
        ),
        migrations.AddConstraint(
            model_name="route",
            constraint=models.CheckConstraint(
                condition=~Q(origin_airport=F("destination_airport")),
                name="route_origin_ne_destination",
            ),
        ),
        migrations.AddConstraint(
            model_name="flightschedule",
            constraint=models.CheckConstraint(
                condition=Q(effective_to__gte=F("effective_from")),
                name="schedule_effective_range_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="flight",
            constraint=models.UniqueConstraint(
                fields=("airline", "flight_number", "departure_utc"), name="uniq_flight_departure"
            ),
        ),
        migrations.AddConstraint(
            model_name="flight",
            constraint=models.CheckConstraint(
                condition=Q(arrival_utc__gt=F("departure_utc")),
                name="flight_arrives_after_departure",
            ),
        ),
        migrations.AddConstraint(
            model_name="cabinconfig",
            constraint=models.UniqueConstraint(
                fields=("flight", "cabin"), name="uniq_flight_cabin"
            ),
        ),
        migrations.AddConstraint(
            model_name="cabinconfig",
            constraint=models.CheckConstraint(
                condition=Q(seats_sold__gte=0) & Q(seats_held__gte=0),
                name="cabin_counts_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="cabinconfig",
            constraint=models.CheckConstraint(
                condition=Q(seats_sold__lte=F("capacity") + F("oversell_allowance")),
                name="cabin_not_oversold",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookingclass",
            constraint=models.UniqueConstraint(fields=("flight", "rbd"), name="uniq_flight_rbd"),
        ),
        migrations.AddConstraint(
            model_name="bookingclass",
            constraint=models.CheckConstraint(
                condition=Q(sold__lte=F("authorised")), name="rbd_not_oversold"
            ),
        ),
        migrations.AddConstraint(
            model_name="bookingclass",
            constraint=models.CheckConstraint(
                condition=Q(sold__gte=0) & Q(held__gte=0), name="rbd_counts_non_negative"
            ),
        ),
        migrations.AddConstraint(
            model_name="seat",
            constraint=models.UniqueConstraint(
                fields=("flight", "seat_number"), name="uniq_flight_seat"
            ),
        ),
    ]
