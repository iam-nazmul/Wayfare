from rest_framework import serializers

from apps.catalog.serializers import AirportSerializer

from .models import (
    BookingClass,
    CabinConfig,
    Flight,
    FlightSchedule,
    Route,
    Seat,
    SeatMapTemplate,
)


class BookingClassSerializer(serializers.ModelSerializer):
    seats_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = BookingClass
        fields = ["id", "rbd", "authorised", "sold", "held", "seats_available",
                  "is_open", "sort_order"]
        read_only_fields = ["id", "sold", "held", "seats_available"]


class CabinConfigSerializer(serializers.ModelSerializer):
    seats_available = serializers.IntegerField(read_only=True)
    booking_classes = BookingClassSerializer(many=True, read_only=True)

    class Meta:
        model = CabinConfig
        fields = ["id", "cabin", "capacity", "seats_sold", "seats_held",
                  "oversell_allowance", "seats_available", "booking_classes"]
        read_only_fields = ["id", "seats_sold", "seats_held", "seats_available"]


class FlightSerializer(serializers.ModelSerializer):
    airline = serializers.CharField(source="airline_id", read_only=True)
    origin = serializers.CharField(source="origin_airport_id", read_only=True)
    destination = serializers.CharField(source="destination_airport_id", read_only=True)
    designator = serializers.CharField(read_only=True)

    class Meta:
        model = Flight
        fields = [
            "public_id", "designator", "airline", "flight_number", "origin", "destination",
            "departure_utc", "arrival_utc", "departure_local", "arrival_local",
            "duration_minutes", "status", "gate", "terminal", "delay_minutes",
        ]
        read_only_fields = fields


class FlightDetailSerializer(FlightSerializer):
    """See ``FlightSerializer``; adds nested inventory and the full airport records."""

    origin_airport = AirportSerializer(read_only=True)
    destination_airport = AirportSerializer(read_only=True)
    cabins = CabinConfigSerializer(many=True, read_only=True)

    class Meta(FlightSerializer.Meta):
        fields = [*FlightSerializer.Meta.fields, "origin_airport", "destination_airport", "cabins"]
        read_only_fields = fields


class FlightOpsSerializer(serializers.ModelSerializer):
    """Writable ops view — only the operational fields, never the inventory counters."""

    class Meta:
        model = Flight
        fields = ["public_id", "status", "gate", "terminal", "delay_minutes",
                  "actual_departure_utc"]
        read_only_fields = ["public_id"]


class SeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = ["seat_number", "row", "column", "cabin", "characteristics",
                  "is_exit_row", "status", "seat_fee_amount", "seat_fee_currency"]
        read_only_fields = fields


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = ["id", "airline", "origin_airport", "destination_airport", "is_active"]


class SeatMapTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeatMapTemplate
        fields = ["id", "name", "aircraft", "layout"]


class FlightScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FlightSchedule
        fields = [
            "id", "airline", "flight_number", "route", "aircraft", "seat_map_template",
            "dep_time_local", "arr_time_local", "arrival_day_offset", "days_of_week",
            "effective_from", "effective_to", "status", "default_cabin_capacity",
        ]

    def validate_days_of_week(self, value: list[bool]) -> list[bool]:
        if len(value) != 7:
            raise serializers.ValidationError("Expected exactly 7 booleans, Monday first.")
        if not any(value):
            raise serializers.ValidationError("A schedule must operate on at least one day.")
        return value

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("effective_from") or getattr(self.instance, "effective_from", None)
        end = attrs.get("effective_to") or getattr(self.instance, "effective_to", None)
        if start and end and end < start:
            raise serializers.ValidationError(
                {"effective_to": "Must be on or after effective_from."}
            )
        return attrs


class MaterialiseSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=365, default=90)


class InventoryUpdateSerializer(serializers.Serializer):
    """Ops edit of the RBD ladder. Sold and held are never client-writable."""

    cabin = serializers.CharField()
    capacity = serializers.IntegerField(min_value=0, max_value=1000, required=False)
    oversell_allowance = serializers.IntegerField(min_value=0, max_value=50, required=False)
    booking_classes = serializers.ListField(child=serializers.DictField(), required=False)
