from django.utils import timezone
from rest_framework import serializers

from apps.inventory.constants import Cabin
from apps.pricing.constants import TripType

from .models import Offer, SearchQuery


class SliceSerializer(serializers.Serializer):
    origin = serializers.CharField(min_length=3, max_length=3)
    destination = serializers.CharField(min_length=3, max_length=3)
    date = serializers.DateField()

    def validate(self, attrs: dict) -> dict:
        if attrs["origin"].upper() == attrs["destination"].upper():
            raise serializers.ValidationError(
                {"destination": "Origin and destination must differ."}
            )
        if attrs["date"] < timezone.now().date():
            raise serializers.ValidationError({"date": "Cannot search for a past date."})
        return attrs


class PassengersSerializer(serializers.Serializer):
    adults = serializers.IntegerField(min_value=1, max_value=9, default=1)
    children = serializers.IntegerField(min_value=0, max_value=8, default=0)
    infants = serializers.IntegerField(min_value=0, max_value=9, default=0)

    def validate(self, attrs: dict) -> dict:
        adults = attrs.get("adults", 1)
        infants = attrs.get("infants", 0)
        if infants > adults:
            raise serializers.ValidationError(
                {"infants": "Each infant must travel with an adult."}
            )
        if adults + attrs.get("children", 0) > 9:
            raise serializers.ValidationError(
                {"adults": "A single booking may carry at most 9 seated passengers."}
            )
        return attrs


class SearchRequestSerializer(serializers.Serializer):
    trip_type = serializers.ChoiceField(choices=TripType.choices, default=TripType.ONE_WAY)
    slices = SliceSerializer(many=True, min_length=1, max_length=6)
    passengers = PassengersSerializer()
    cabin = serializers.ChoiceField(choices=Cabin.choices, default=Cabin.ECONOMY)
    currency = serializers.CharField(max_length=3, default="USD")
    max_stops = serializers.IntegerField(min_value=0, max_value=2, default=1)

    def validate(self, attrs: dict) -> dict:
        trip_type, slices = attrs["trip_type"], attrs["slices"]

        if trip_type == TripType.ONE_WAY and len(slices) != 1:
            raise serializers.ValidationError({"slices": "A one-way trip has exactly one slice."})
        if trip_type == TripType.ROUND_TRIP:
            if len(slices) != 2:
                raise serializers.ValidationError({"slices": "A round trip has two slices."})
            if slices[1]["date"] < slices[0]["date"]:
                raise serializers.ValidationError(
                    {"slices": "The return date cannot be before the outbound date."}
                )
        return attrs


class OfferSerializer(serializers.ModelSerializer):
    offer_id = serializers.UUIDField(read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            "offer_id", "itinerary", "price_breakdown", "total", "currency",
            "seats_remaining", "expires_at",
        ]
        read_only_fields = fields

    def get_total(self, obj: Offer) -> dict[str, str]:
        return {"amount": str(obj.total_amount), "currency": obj.currency}


class SearchSliceResultSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    search_id = serializers.UUIDField()
    origin = serializers.CharField()
    destination = serializers.CharField()
    date = serializers.DateField()
    offers = OfferSerializer(many=True)


class SearchResponseSerializer(serializers.Serializer):
    trip_type = serializers.CharField()
    currency = serializers.CharField()
    partial = serializers.BooleanField()
    slices = SearchSliceResultSerializer(many=True)


class SearchQuerySerializer(serializers.ModelSerializer):
    search_id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = SearchQuery
        fields = [
            "search_id", "origin", "destination", "depart_date", "return_date",
            "trip_type", "cabin", "currency", "results_count", "cache_hit", "latency_ms",
        ]
        read_only_fields = fields


class CalendarEntrySerializer(serializers.Serializer):
    date = serializers.DateField()
    cheapest = serializers.DictField(child=serializers.CharField(), allow_null=True)
