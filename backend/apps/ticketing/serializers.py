from rest_framework import serializers

from apps.common.fields import MoneyField

from .models import Ticket, TicketCoupon


class TicketCouponSerializer(serializers.ModelSerializer):
    designator = serializers.CharField(
        source="segment.marketing_flight_number", read_only=True
    )
    origin = serializers.CharField(source="segment.flight.origin_airport_id", read_only=True)
    destination = serializers.CharField(
        source="segment.flight.destination_airport_id", read_only=True
    )
    departure_local = serializers.DateTimeField(
        source="segment.flight.departure_local", read_only=True
    )
    #: A coupon without an arrival time is not a document anyone can travel on.
    arrival_local = serializers.DateTimeField(
        source="segment.flight.arrival_local", read_only=True
    )
    duration_minutes = serializers.IntegerField(
        source="segment.flight.duration_minutes", read_only=True
    )
    cabin = serializers.CharField(source="segment.cabin", read_only=True)
    rbd = serializers.CharField(source="segment.rbd", read_only=True)
    fare_basis = serializers.CharField(source="segment.fare_basis", read_only=True)

    class Meta:
        model = TicketCoupon
        fields = [
            "coupon_number", "status", "designator", "origin", "destination",
            "departure_local", "arrival_local", "duration_minutes",
            "cabin", "rbd", "fare_basis", "flown_at",
        ]
        read_only_fields = fields


class TicketSerializer(serializers.ModelSerializer):
    passenger_name = serializers.SerializerMethodField()
    fare = MoneyField("fare_amount", read_only=True, source="*")
    taxes = MoneyField("tax_amount", read_only=True, source="*")
    total = MoneyField("total_amount", read_only=True, source="*")
    coupons = TicketCouponSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "ticket_number", "status", "passenger_name", "issued_at",
            "fare", "taxes", "total", "fare_calculation", "coupons",
        ]
        read_only_fields = fields

    def get_passenger_name(self, ticket: Ticket) -> str:
        return f"{ticket.passenger.last_name}/{ticket.passenger.first_name}"
