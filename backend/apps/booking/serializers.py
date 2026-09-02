from collections import Counter
from datetime import date

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.constants import DocumentType, Gender
from apps.common.fields import MoneyField
from apps.inventory.constants import Cabin
from apps.pricing.constants import PassengerType, TripType

from .models import Booking, BookingSegment, Offer, Passenger, SearchQuery
from .services.pax import pax_type_for


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


class PassengerInputSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=PassengerType.choices)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    dob = serializers.DateField()
    gender = serializers.ChoiceField(choices=Gender.choices, required=False, allow_blank=True)
    nationality = serializers.CharField(max_length=2, required=False, allow_blank=True)
    doc_type = serializers.ChoiceField(
        choices=DocumentType.choices, required=False, allow_blank=True
    )
    doc_number = serializers.CharField(max_length=64, required=False, allow_blank=True)
    doc_expiry = serializers.DateField(required=False, allow_null=True)
    frequent_flyer_number = serializers.CharField(
        max_length=32, required=False, allow_blank=True
    )


class ContactSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)


class BookingCreateSerializer(serializers.Serializer):
    """One offer per journey slice — a round trip books both legs into a single PNR.

    ``offer_id`` is the one-slice shorthand; ``offer_ids`` carries a multi-slice journey in
    travel order. Exactly one of the two must be given.
    """

    offer_id = serializers.UUIDField(required=False)
    offer_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, min_length=1, max_length=6
    )
    passengers = PassengerInputSerializer(many=True, min_length=1, max_length=9)
    contact = ContactSerializer()

    def validate(self, attrs: dict) -> dict:
        single, many = attrs.get("offer_id"), attrs.get("offer_ids")

        if not single and not many:
            raise serializers.ValidationError(
                {"offer_ids": "Give an offer for each slice of the journey."}
            )
        if single and many:
            raise serializers.ValidationError(
                {"offer_ids": "Send either offer_id or offer_ids, not both."}
            )

        offers = many or [single]
        if len(set(offers)) != len(offers):
            raise serializers.ValidationError(
                {"offer_ids": "The same offer cannot be used for two slices."}
            )

        attrs["offer_ids"] = offers
        return attrs

    def validate_passengers(self, passengers: list[dict]) -> list[dict]:
        counts = Counter(entry["type"] for entry in passengers)

        if counts[PassengerType.ADULT] == 0:
            raise serializers.ValidationError("Every booking needs at least one adult.")
        if counts[PassengerType.INFANT] > counts[PassengerType.ADULT]:
            raise serializers.ValidationError(
                "Each infant must travel with its own adult."
            )
        if counts[PassengerType.ADULT] + counts[PassengerType.CHILD] > 9:
            raise serializers.ValidationError(
                "A single booking may carry at most 9 seated passengers."
            )

        for index, entry in enumerate(passengers):
            expected = pax_type_for(entry["dob"], self.reference_date)
            if expected != entry["type"]:
                raise serializers.ValidationError(
                    {
                        str(index): (
                            f"A passenger born {entry['dob']} travels as "
                            f"{PassengerType(expected).label.lower()}, not "
                            f"{PassengerType(entry['type']).label.lower()}."
                        )
                    }
                )

        return passengers

    @property
    def reference_date(self) -> date:
        """Passenger type is derived at the *return* date — a child can turn 12 mid-journey."""
        return self.context.get("reference_date") or timezone.now().date()


class BookingSegmentSerializer(serializers.ModelSerializer):
    flight_public_id = serializers.UUIDField(source="flight.public_id", read_only=True)
    designator = serializers.CharField(source="marketing_flight_number", read_only=True)
    origin = serializers.CharField(source="flight.origin_airport_id", read_only=True)
    destination = serializers.CharField(source="flight.destination_airport_id", read_only=True)
    departure_utc = serializers.DateTimeField(source="flight.departure_utc", read_only=True)
    arrival_utc = serializers.DateTimeField(source="flight.arrival_utc", read_only=True)
    departure_local = serializers.DateTimeField(source="flight.departure_local", read_only=True)
    arrival_local = serializers.DateTimeField(source="flight.arrival_local", read_only=True)
    duration_minutes = serializers.IntegerField(
        source="flight.duration_minutes", read_only=True
    )

    class Meta:
        model = BookingSegment
        fields = [
            "sequence", "flight_public_id", "designator", "origin", "destination",
            "departure_utc", "arrival_utc", "departure_local", "arrival_local",
            "duration_minutes", "cabin", "rbd", "fare_basis", "status",
            "baggage_allowance",
        ]
        read_only_fields = fields


class PassengerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Passenger
        fields = [
            "id", "type", "first_name", "last_name", "dob", "gender", "nationality",
            "doc_type", "doc_number", "doc_expiry", "frequent_flyer_number",
        ]
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    base = MoneyField("base_amount", read_only=True, source="*")
    taxes = MoneyField("tax_amount", read_only=True, source="*")
    fees = MoneyField("fee_amount", read_only=True, source="*")
    discount = MoneyField("discount_amount", read_only=True, source="*")
    total = MoneyField("total_amount", read_only=True, source="*")
    balance_due = MoneyField("balance_due", read_only=True, source="*")
    segments = BookingSegmentSerializer(many=True, read_only=True)
    passengers = PassengerSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "pnr", "public_id", "status", "trip_type", "currency",
            "base", "taxes", "fees", "discount", "total", "balance_due",
            "contact_email", "contact_phone", "hold_expires_at", "booked_at",
            "segments", "passengers",
        ]
        read_only_fields = fields


class MoneyOutSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)


class RefundQuoteSerializer(serializers.Serializer):
    paid = MoneyOutSerializer()
    penalty = MoneyOutSerializer()
    non_refundable_tax = MoneyOutSerializer()
    refundable = MoneyOutSerializer()
    refundable_fare = serializers.BooleanField()
    reason = serializers.CharField()


class CancelRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    #: Ask for the quote without cancelling. The traveller sees the penalty before committing.
    quote_only = serializers.BooleanField(default=False)


class CancelResponseSerializer(serializers.Serializer):
    booking = BookingSerializer()
    quote = RefundQuoteSerializer()
    voided = serializers.BooleanField()
    refund_id = serializers.UUIDField(allow_null=True)
    refund_status = serializers.CharField(allow_null=True)


class ChangeRequestSerializer(serializers.Serializer):
    offer_id = serializers.UUIDField()


class ChangeQuoteSerializer(serializers.Serializer):
    old_total = MoneyOutSerializer()
    new_total = MoneyOutSerializer()
    fare_difference = MoneyOutSerializer()
    change_fee = MoneyOutSerializer()
    amount_due = MoneyOutSerializer()
    residual = MoneyOutSerializer()
    changeable = serializers.BooleanField()
    reason = serializers.CharField()


class ChangeConfirmResponseSerializer(serializers.Serializer):
    booking = BookingSerializer()
    quote = ChangeQuoteSerializer()
