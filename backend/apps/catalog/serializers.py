from rest_framework import serializers

from .models import Aircraft, Airline, Airport, Currency


class AirportSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    country = serializers.CharField(source="country.name", read_only=True)
    country_code = serializers.CharField(source="country_id", read_only=True)

    class Meta:
        model = Airport
        fields = [
            "iata_code", "icao_code", "name", "city", "country", "country_code",
            "timezone", "latitude", "longitude",
        ]


class AirlineSerializer(serializers.ModelSerializer):
    country = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = Airline
        fields = ["iata_code", "icao_code", "name", "country", "logo_url"]


class AircraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Aircraft
        fields = ["iata_type_code", "name", "manufacturer", "total_seats_default"]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ["code", "name", "symbol", "minor_units"]
