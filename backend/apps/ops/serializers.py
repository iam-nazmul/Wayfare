from rest_framework import serializers

from apps.common.fields import MoneyField

from .models import Disruption, RebookOption


class DisruptionSerializer(serializers.ModelSerializer):
    disruption_id = serializers.UUIDField(source="public_id", read_only=True)
    flight = serializers.CharField(source="flight.designator", read_only=True)

    class Meta:
        model = Disruption
        fields = [
            "disruption_id", "flight", "type", "reason", "delay_minutes",
            "detected_at", "resolved_at",
        ]
        read_only_fields = fields


class RebookOptionSerializer(serializers.ModelSerializer):
    option_id = serializers.UUIDField(source="public_id", read_only=True)
    designator = serializers.CharField(source="proposed_flight.designator", read_only=True)
    origin = serializers.CharField(
        source="proposed_flight.origin_airport_id", read_only=True
    )
    destination = serializers.CharField(
        source="proposed_flight.destination_airport_id", read_only=True
    )
    departure_local = serializers.DateTimeField(
        source="proposed_flight.departure_local", read_only=True
    )
    arrival_local = serializers.DateTimeField(
        source="proposed_flight.arrival_local", read_only=True
    )
    duration_minutes = serializers.IntegerField(
        source="proposed_flight.duration_minutes", read_only=True
    )
    fare_delta = MoneyField("fare_delta", read_only=True, source="*")
    disrupted_flight = serializers.CharField(
        source="disruption.flight.designator", read_only=True
    )
    disruption_type = serializers.CharField(source="disruption.type", read_only=True)
    reason = serializers.CharField(source="disruption.reason", read_only=True)

    class Meta:
        model = RebookOption
        fields = [
            "option_id", "rank", "status", "designator", "origin", "destination",
            "departure_local", "arrival_local", "duration_minutes", "cabin",
            "fare_delta", "expires_at", "disrupted_flight", "disruption_type", "reason",
        ]
        read_only_fields = fields


class RebookRequestSerializer(serializers.Serializer):
    option_id = serializers.UUIDField()
