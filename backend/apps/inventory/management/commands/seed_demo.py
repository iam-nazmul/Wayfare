from datetime import date, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import RoleCode
from apps.accounts.models import Agency, User, UserRole
from apps.catalog.models import Aircraft, Airline, Airport, City, Country, Currency
from apps.inventory.constants import ScheduleStatus
from apps.inventory.models import FlightSchedule, Route, SeatMapTemplate
from apps.inventory.services.materialise import materialise_schedule

DEMO_PASSWORD = "wayfare-demo-1"

COUNTRIES = [
    ("BD", "BGD", "Bangladesh", "+880"),
    ("AE", "ARE", "United Arab Emirates", "+971"),
    ("GB", "GBR", "United Kingdom", "+44"),
    ("US", "USA", "United States", "+1"),
    ("SG", "SGP", "Singapore", "+65"),
    ("IN", "IND", "India", "+91"),
    ("TH", "THA", "Thailand", "+66"),
    ("QA", "QAT", "Qatar", "+974"),
]

# (iata, name, city, country, timezone, lat, lon)
AIRPORTS = [
    ("DAC", "Hazrat Shahjalal International", "Dhaka", "BD", "Asia/Dhaka", 23.843, 90.398),
    ("CGP", "Shah Amanat International", "Chattogram", "BD", "Asia/Dhaka", 22.249, 91.813),
    ("ZYL", "Osmani International", "Sylhet", "BD", "Asia/Dhaka", 24.963, 91.867),
    ("CXB", "Cox's Bazar", "Cox's Bazar", "BD", "Asia/Dhaka", 21.452, 91.964),
    ("DXB", "Dubai International", "Dubai", "AE", "Asia/Dubai", 25.253, 55.365),
    ("AUH", "Zayed International", "Abu Dhabi", "AE", "Asia/Dubai", 24.433, 54.651),
    ("DOH", "Hamad International", "Doha", "QA", "Asia/Qatar", 25.273, 51.608),
    ("LHR", "Heathrow", "London", "GB", "Europe/London", 51.470, -0.454),
    ("LGW", "Gatwick", "London", "GB", "Europe/London", 51.148, -0.190),
    ("MAN", "Manchester", "Manchester", "GB", "Europe/London", 53.365, -2.272),
    ("JFK", "John F. Kennedy International", "New York", "US", "America/New_York", 40.641, -73.778),
    ("LAX", "Los Angeles International", "Los Angeles", "US", "America/Los_Angeles", 33.942, -118.408),
    ("SIN", "Changi", "Singapore", "SG", "Asia/Singapore", 1.364, 103.991),
    ("DEL", "Indira Gandhi International", "Delhi", "IN", "Asia/Kolkata", 28.556, 77.100),
    ("BOM", "Chhatrapati Shivaji Maharaj", "Mumbai", "IN", "Asia/Kolkata", 19.089, 72.868),
    ("BKK", "Suvarnabhumi", "Bangkok", "TH", "Asia/Bangkok", 13.690, 100.750),
]

AIRLINES = [
    ("WF", "WYF", "Wayfare Airways", "BD", "176"),
    ("BS", "BBC", "Bengal Skyways", "BD", "804"),
    ("GX", "GLX", "Gulf Express", "AE", "607"),
    ("NA", "NAT", "Northern Atlantic", "GB", "125"),
]

AIRCRAFT = [
    ("32N", "Airbus A320neo", "Airbus", 180),
    ("789", "Boeing 787-9 Dreamliner", "Boeing", 290),
    ("77W", "Boeing 777-300ER", "Boeing", 350),
    ("AT7", "ATR 72-600", "ATR", 72),
]

CURRENCIES = [
    ("USD", "US Dollar", "$"),
    ("BDT", "Bangladeshi Taka", "৳"),
    ("GBP", "Pound Sterling", "£"),
    ("AED", "UAE Dirham", "د.إ"),
    ("EUR", "Euro", "€"),
]

# (airline, number, origin, destination, dep, arr, day_offset, aircraft, capacity)
SCHEDULES = [
    ("WF", "101", "DAC", "DXB", time(2, 30), time(5, 45), 0, "32N", {"ECONOMY": 156, "BUSINESS": 16}),
    ("WF", "102", "DXB", "DAC", time(8, 30), time(15, 40), 0, "32N", {"ECONOMY": 156, "BUSINESS": 16}),
    ("WF", "201", "DAC", "LHR", time(9, 15), time(15, 30), 0, "789", {"ECONOMY": 240, "PREMIUM_ECONOMY": 28, "BUSINESS": 22}),
    ("WF", "202", "LHR", "DAC", time(19, 45), time(13, 20), 1, "789", {"ECONOMY": 240, "PREMIUM_ECONOMY": 28, "BUSINESS": 22}),
    ("WF", "310", "DAC", "CGP", time(7, 0), time(8, 0), 0, "AT7", {"ECONOMY": 72}),
    ("WF", "311", "CGP", "DAC", time(9, 0), time(10, 0), 0, "AT7", {"ECONOMY": 72}),
    ("WF", "320", "DAC", "CXB", time(11, 30), time(12, 40), 0, "AT7", {"ECONOMY": 72}),
    ("WF", "321", "CXB", "DAC", time(13, 30), time(14, 40), 0, "AT7", {"ECONOMY": 72}),
    ("BS", "440", "DAC", "SIN", time(23, 55), time(6, 30), 1, "32N", {"ECONOMY": 168}),
    ("BS", "441", "SIN", "DAC", time(8, 20), time(10, 15), 0, "32N", {"ECONOMY": 168}),
    ("GX", "550", "DXB", "LHR", time(3, 10), time(7, 25), 0, "77W", {"ECONOMY": 300, "BUSINESS": 42}),
    ("GX", "551", "LHR", "DXB", time(10, 5), time(20, 30), 0, "77W", {"ECONOMY": 300, "BUSINESS": 42}),
    ("GX", "560", "DXB", "DEL", time(9, 40), time(14, 25), 0, "32N", {"ECONOMY": 174}),
    ("NA", "700", "LHR", "JFK", time(11, 0), time(14, 10), 0, "789", {"ECONOMY": 250, "BUSINESS": 40}),
    ("NA", "701", "JFK", "LHR", time(21, 30), time(9, 40), 1, "789", {"ECONOMY": 250, "BUSINESS": 40}),
    ("NA", "720", "LHR", "BKK", time(12, 30), time(6, 45), 1, "77W", {"ECONOMY": 310, "BUSINESS": 32}),
]

SEAT_MAPS = {
    "32N": {
        "cabins": [
            {"cabin": "BUSINESS", "rows": [1, 4], "columns": "AC DF", "seat_fee": 0},
            {"cabin": "ECONOMY", "rows": [10, 35], "columns": "ABC DEF",
             "exit_rows": [14, 15], "seat_fee": 12},
        ]
    },
    "789": {
        "cabins": [
            {"cabin": "BUSINESS", "rows": [1, 6], "columns": "AC DG HK", "seat_fee": 0},
            {"cabin": "PREMIUM_ECONOMY", "rows": [10, 14], "columns": "ABC DEF GHK",
             "seat_fee": 25},
            {"cabin": "ECONOMY", "rows": [20, 45], "columns": "ABC DEF GHK",
             "exit_rows": [20, 30], "seat_fee": 18},
        ]
    },
    "77W": {
        "cabins": [
            {"cabin": "BUSINESS", "rows": [1, 8], "columns": "AC DG HK", "seat_fee": 0},
            {"cabin": "ECONOMY", "rows": [20, 50], "columns": "ABC DEFG HJK",
             "exit_rows": [20, 35], "seat_fee": 20},
        ]
    },
    "AT7": {
        "cabins": [
            {"cabin": "ECONOMY", "rows": [1, 18], "columns": "AB CD",
             "exit_rows": [10], "seat_fee": 6},
        ]
    },
}


class Command(BaseCommand):
    help = "Load demo catalog, inventory and users. Idempotent — safe to re-run."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=90, help="Days of flights to materialise")

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        self.stdout.write("seeding catalog…")
        self._catalog()

        self.stdout.write("seeding users…")
        self._users()

        self.stdout.write("seeding schedules…")
        schedules = self._schedules()

        days = options["days"]
        self.stdout.write(f"materialising {days} days of flights…")
        start = timezone.now().date()
        end = start + timedelta(days=days)
        created = skipped = 0
        for schedule in schedules:
            made, missed = materialise_schedule(schedule, start, end)
            created += made
            skipped += missed

        self.stdout.write(
            self.style.SUCCESS(
                f"seeded {len(AIRPORTS)} airports, {len(AIRLINES)} airlines, "
                f"{len(schedules)} schedules, {created} flights ({skipped} already present)"
            )
        )
        self.stdout.write(f"demo login: demo@wayfare.local / {DEMO_PASSWORD}")

    def _catalog(self) -> None:
        for iso2, iso3, name, prefix in COUNTRIES:
            Country.objects.update_or_create(
                iso2=iso2, defaults={"iso3": iso3, "name": name, "phone_prefix": prefix}
            )

        for code, name, symbol in CURRENCIES:
            Currency.objects.update_or_create(code=code, defaults={"name": name, "symbol": symbol})

        for type_code, name, manufacturer, seats in AIRCRAFT:
            Aircraft.objects.update_or_create(
                iata_type_code=type_code,
                defaults={
                    "name": name,
                    "manufacturer": manufacturer,
                    "total_seats_default": seats,
                },
            )

        for iata, name, city_name, country, tz, lat, lon in AIRPORTS:
            city, _ = City.objects.get_or_create(
                name=city_name, country_id=country, defaults={"timezone": tz}
            )
            Airport.objects.update_or_create(
                iata_code=iata,
                defaults={
                    "name": name,
                    "city": city,
                    "country_id": country,
                    "timezone": tz,
                    "latitude": lat,
                    "longitude": lon,
                },
            )

        for iata, icao, name, country, prefix in AIRLINES:
            Airline.objects.update_or_create(
                iata_code=iata,
                defaults={
                    "icao_code": icao,
                    "name": name,
                    "country_id": country,
                    "ticketing_prefix": prefix,
                },
            )

    def _users(self) -> None:
        agency, _ = Agency.objects.get_or_create(
            name="Skyline Travel",
            defaults={"iata_code": "91234567", "currency": "USD", "credit_limit": 25_000},
        )

        accounts = [
            ("demo@wayfare.local", "Demo", "Traveller", RoleCode.TRAVELLER, None, False),
            ("agency@wayfare.local", "Agency", "Agent", RoleCode.AGENCY_AGENT, agency, False),
            ("ops@wayfare.local", "Airline", "Ops", RoleCode.OPS_AGENT, None, True),
        ]

        for email, first, last, role, user_agency, is_staff in accounts:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(
                    email=email,
                    password=DEMO_PASSWORD,
                    first_name=first,
                    last_name=last,
                    is_staff=is_staff,
                )
            UserRole.objects.get_or_create(user=user, role=role, agency=user_agency)

        if not User.objects.filter(email="admin@wayfare.local").exists():
            User.objects.create_superuser(
                email="admin@wayfare.local", password=DEMO_PASSWORD,
                first_name="Site", last_name="Admin",
            )

    def _schedules(self) -> list[FlightSchedule]:
        templates = {}
        for type_code, layout in SEAT_MAPS.items():
            aircraft = Aircraft.objects.get(iata_type_code=type_code)
            template, _ = SeatMapTemplate.objects.update_or_create(
                name=f"{type_code} standard", aircraft=aircraft, defaults={"layout": layout}
            )
            templates[type_code] = template

        today = date.today()
        schedules = []

        for airline, number, origin, dest, dep, arr, offset, type_code, capacity in SCHEDULES:
            route, _ = Route.objects.get_or_create(
                airline_id=airline, origin_airport_id=origin, destination_airport_id=dest
            )
            schedule, _ = FlightSchedule.objects.update_or_create(
                airline_id=airline,
                flight_number=number,
                route=route,
                defaults={
                    "aircraft": Aircraft.objects.get(iata_type_code=type_code),
                    "seat_map_template": templates[type_code],
                    "dep_time_local": dep,
                    "arr_time_local": arr,
                    "arrival_day_offset": offset,
                    "days_of_week": [True] * 7,
                    "effective_from": today - timedelta(days=1),
                    "effective_to": today + timedelta(days=365),
                    "status": ScheduleStatus.ACTIVE,
                    "default_cabin_capacity": capacity,
                },
            )
            schedules.append(schedule)

        return schedules
