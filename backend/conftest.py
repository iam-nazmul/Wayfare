from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.catalog.models import Aircraft, Airline, Airport, City, Country, Currency
from apps.inventory.constants import Cabin
from apps.inventory.models import (
    BookingClass,
    CabinConfig,
    Flight,
    FlightSchedule,
    Route,
    SeatMapTemplate,
)
from apps.pricing.constants import FareTier, PassengerType
from apps.pricing.models import Fare, FareFamily


@pytest.fixture
def countries(db):
    return {
        code: Country.objects.create(iso2=code, iso3=iso3, name=name)
        for code, iso3, name in [
            ("BD", "BGD", "Bangladesh"),
            ("AE", "ARE", "United Arab Emirates"),
            ("GB", "GBR", "United Kingdom"),
        ]
    }


@pytest.fixture
def airports(countries):
    made = {}
    for code, name, city_name, country, tz, lat, lon in [
        ("DAC", "Shahjalal", "Dhaka", "BD", "Asia/Dhaka", 23.843, 90.398),
        ("DXB", "Dubai Intl", "Dubai", "AE", "Asia/Dubai", 25.253, 55.365),
        ("LHR", "Heathrow", "London", "GB", "Europe/London", 51.470, -0.454),
    ]:
        city = City.objects.create(name=city_name, country=countries[country], timezone=tz)
        made[code] = Airport.objects.create(
            iata_code=code, name=name, city=city, country=countries[country],
            timezone=tz, latitude=lat, longitude=lon,
        )
    return made


@pytest.fixture
def airline(countries):
    Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar"})
    return Airline.objects.create(
        iata_code="WF", icao_code="WYF", name="Wayfare Airways",
        country=countries["BD"], ticketing_prefix="176",
    )


@pytest.fixture
def aircraft(db):
    return Aircraft.objects.create(
        iata_type_code="32N", name="A320neo", manufacturer="Airbus", total_seats_default=180
    )


@pytest.fixture
def seat_map(aircraft):
    return SeatMapTemplate.objects.create(
        name="32N standard",
        aircraft=aircraft,
        layout={
            "cabins": [
                {"cabin": "ECONOMY", "rows": [10, 12], "columns": "ABC DEF",
                 "exit_rows": [11], "seat_fee": 10}
            ]
        },
    )


@pytest.fixture
def make_flight(airline, airports, aircraft, seat_map):
    """Build a dated flight with cabin capacity and a single RBD bucket."""

    def _make(
        origin="DAC", destination="DXB", *, days_ahead=7, capacity=2, rbd="Y",
        authorised=None, cabin=Cabin.ECONOMY, depart_hour=2, duration_minutes=315,
        flight_number="101",
    ):
        departure_local = datetime.combine(
            date.today() + timedelta(days=days_ahead), time(depart_hour, 30), tzinfo=UTC
        )
        departure_utc = departure_local - timedelta(hours=6)
        arrival_utc = departure_utc + timedelta(minutes=duration_minutes)

        flight = Flight.objects.create(
            airline=airline,
            flight_number=flight_number,
            origin_airport=airports[origin],
            destination_airport=airports[destination],
            aircraft=aircraft,
            seat_map_template=seat_map,
            departure_utc=departure_utc,
            arrival_utc=arrival_utc,
            departure_local=departure_local,
            arrival_local=departure_local + timedelta(minutes=duration_minutes),
            duration_minutes=duration_minutes,
        )
        cabin_config = CabinConfig.objects.create(
            flight=flight, cabin=cabin, capacity=capacity
        )
        BookingClass.objects.create(
            flight=flight, cabin_config=cabin_config, rbd=rbd,
            authorised=capacity if authorised is None else authorised, sort_order=0,
        )
        return flight

    return _make


@pytest.fixture
def fare_family(airline):
    return FareFamily.objects.create(
        airline=airline, code="ECOSTD", name="Economy Standard",
        cabin=Cabin.ECONOMY, tier=FareTier.STANDARD, changeable=True, refundable=False,
    )


@pytest.fixture
def make_fare(airline, airports, fare_family):
    def _make(
        origin="DAC", destination="DXB", *, rbd="Y", amount="200.00",
        passenger_type=PassengerType.ADULT, advance_purchase_days=0,
        min_stay_days=None, max_stay_days=None, cabin=Cabin.ECONOMY,
    ):
        return Fare.objects.create(
            airline=airline,
            origin_airport=airports[origin],
            destination_airport=airports[destination],
            cabin=cabin,
            rbd=rbd,
            fare_family=fare_family,
            fare_basis=f"{rbd}TEST",
            base_amount=Decimal(amount),
            currency="USD",
            passenger_type=passenger_type,
            advance_purchase_days=advance_purchase_days,
            min_stay_days=min_stay_days,
            max_stay_days=max_stay_days,
            valid_from=date.today() - timedelta(days=1),
            valid_to=date.today() + timedelta(days=365),
        )

    return _make


@pytest.fixture
def traveller(db):
    return User.objects.create_user(email="traveller@test.local", password="test-pass-12345")
