"""Ops reports and the mirror sync — SPEC.md §9.5, M7."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.constants import RoleCode
from apps.accounts.models import User, UserRole
from apps.analytics.devices import device_type
from apps.analytics.reports import REPORTS, Report
from apps.analytics.tasks import rollup_daily_metrics, sync_bookings_to_clickhouse

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def ops_agent(db):
    user = User.objects.create_user(email="reports@test.local", password="test-pass-12345")
    UserRole.objects.create(user=user, role=RoleCode.OPS_AGENT)
    return user


@pytest.fixture
def fake_query():
    """Reports are ClickHouse queries; the assertions here are about the API around them."""
    with patch("apps.analytics.reports.query") as mocked:
        mocked.return_value = [["DAC", "DXB", 10, 2, 20.0]]
        yield mocked


# --- device bucketing --------------------------------------------------------


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148", "mobile"),
        ("Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile Safari/537.36", "mobile"),
        ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)", "tablet"),
        ("Mozilla/5.0 (Linux; Android 14; SM-X200) Safari/537.36", "tablet"),
        ("Mozilla/5.0 (X11; Linux x86_64) Chrome/152.0.0.0 Safari/537.36", "desktop"),
        ("Googlebot/2.1 (+http://www.google.com/bot.html)", "bot"),
        ("", "unknown"),
    ],
)
def test_the_device_bucket_is_derived_from_the_user_agent(agent, expected):
    assert device_type(agent) == expected


def test_the_collector_records_the_device(client):
    with patch("apps.analytics.views.push") as push:
        response = client.post(
            reverse("v1:collect"),
            {
                "events": [
                    {"event_name": "page_view", "session_id": "s1", "page_path": "/"}
                ]
            },
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148",
        )

    assert response.status_code == 204
    assert push.call_args.args[1]["device_type"] == "mobile"


# --- report endpoint ---------------------------------------------------------


def test_every_catalogued_report_is_reachable(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)

    for slug in REPORTS:
        cache.clear()
        response = client.get(reverse("v1:ops-report", args=[slug]))
        assert response.status_code == 200, slug
        assert response.data["report"] == slug
        assert "columns" in response.data


def test_an_unknown_report_is_a_404(client, ops_agent):
    client.force_authenticate(ops_agent)
    assert client.get(reverse("v1:ops-report", args=["not-a-report"])).status_code == 404


def test_reports_are_closed_to_travellers(client, traveller):
    client.force_authenticate(traveller)
    assert client.get(reverse("v1:ops-report", args=["revenue"])).status_code == 403


def test_reports_are_closed_to_anonymous_callers(client):
    assert client.get(reverse("v1:ops-report", args=["revenue"])).status_code in (401, 403)


def test_the_window_defaults_to_the_last_thirty_days(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)
    response = client.get(reverse("v1:ops-report", args=["top-routes"]))

    span = response.data["date_to"] - response.data["date_from"]
    assert span == timedelta(days=30)


def test_a_window_wider_than_four_hundred_days_is_rejected(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)
    response = client.get(
        reverse("v1:ops-report", args=["revenue"]),
        {"date_from": "2020-01-01", "date_to": "2026-01-01"},
    )

    assert response.status_code == 422
    assert response.data["code"] == "validation_error"


def test_a_backwards_window_is_rejected(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)
    response = client.get(
        reverse("v1:ops-report", args=["revenue"]),
        {"date_from": "2026-06-01", "date_to": "2026-05-01"},
    )

    assert response.status_code == 422


def test_a_report_is_cached_for_five_minutes(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)
    url = reverse("v1:ops-report", args=["top-routes"])

    client.get(url)
    client.get(url)

    # Second call served from Redis, so ClickHouse is hit once.
    assert fake_query.call_count == 1


def test_a_different_window_is_a_different_cache_entry(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)
    url = reverse("v1:ops-report", args=["top-routes"])

    client.get(url, {"date_from": "2026-01-01", "date_to": "2026-01-31"})
    client.get(url, {"date_from": "2026-02-01", "date_to": "2026-02-28"})

    assert fake_query.call_count == 2


def test_csv_is_streamed_when_asked_for(client, ops_agent, fake_query):
    client.force_authenticate(ops_agent)
    response = client.get(
        reverse("v1:ops-report", args=["top-routes"]), HTTP_ACCEPT="text/csv"
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "top-routes.csv" in response["Content-Disposition"]

    body = b"".join(response.streaming_content).decode()
    assert body.splitlines()[0] == "origin,destination,searches,sessions,avg_cheapest"
    assert "DAC,DXB,10,2,20.0" in body


def test_the_funnel_returns_its_steps_in_conversion_order(client, ops_agent):
    with patch("apps.analytics.reports.query") as mocked:
        mocked.return_value = [
            ["booking_confirmed", "mobile", 5, 5],
            ["page_view", "mobile", 100, 400],
            ["payment_started", "mobile", 8, 9],
            ["search_submitted", "mobile", 60, 90],
        ]
        client.force_authenticate(ops_agent)
        response = client.get(reverse("v1:ops-report", args=["funnel"]))

    steps = [row[0] for row in response.data["rows"]]
    assert steps == [
        "page_view",
        "search_submitted",
        "payment_started",
        "booking_confirmed",
    ]


def test_load_factor_reads_live_inventory(client, ops_agent, make_flight):
    """Not the mirror: ops must not size capacity from yesterday's snapshot."""
    from apps.inventory.models import CabinConfig

    flight = make_flight(days_ahead=3, capacity=100, rbd="Y")
    CabinConfig.objects.filter(flight=flight).update(seats_sold=25, seats_held=5)

    client.force_authenticate(ops_agent)
    response = client.get(
        reverse("v1:ops-report", args=["load-factor"]),
        {
            "date_from": (date.today()).isoformat(),
            "date_to": (date.today() + timedelta(days=10)).isoformat(),
        },
    )

    assert response.status_code == 200
    row = response.data["rows"][0]
    assert row[5:8] == [100, 25, 5]
    assert row[8] == 25.0


# --- mirror sync -------------------------------------------------------------


@pytest.fixture
def booking(make_flight, make_fare, db):
    from apps.booking.constants import BookingStatus
    from apps.booking.models import Booking, BookingSegment, Passenger

    flight = make_flight(days_ahead=10, capacity=10, rbd="Y")
    entry = Booking.objects.create(
        pnr="MIR001",
        status=BookingStatus.TICKETED,
        contact_email="m@example.com",
        base_amount=Decimal("200.00"),
        tax_amount=Decimal("30.00"),
        total_amount=Decimal("230.00"),
        paid_amount=Decimal("230.00"),
        currency="USD",
    )
    BookingSegment.objects.create(
        booking=entry, flight=flight, sequence=0, cabin="ECONOMY", rbd="Y",
        marketing_flight_number=flight.designator,
    )
    Passenger.objects.create(
        booking=entry, type="ADT", first_name="A", last_name="B", dob=date(1990, 1, 1)
    )
    Passenger.objects.create(
        booking=entry, type="INF", first_name="C", last_name="B", dob=date(2025, 1, 1)
    )
    return entry


def test_the_mirror_sends_one_row_per_booking(booking):
    with patch("apps.analytics.tasks.insert_rows", return_value=1) as insert:
        assert sync_bookings_to_clickhouse(full=True) == 1

    table, rows, columns = insert.call_args.args
    assert table == "wayfare.bookings_mirror"
    assert len(rows) == 1
    assert len(rows[0]) == len(columns)

    row = dict(zip(columns, rows[0], strict=True))
    assert row["pnr"] == "MIR001"
    assert row["origin"] == "DAC"
    assert row["destination"] == "DXB"
    # The infant has no seat, so it is not a passenger for revenue purposes.
    assert row["pax_count"] == 1
    assert row["total_amount_usd"] == Decimal("230.00")


def test_the_mirror_is_incremental(booking):
    with patch("apps.analytics.tasks.insert_rows", return_value=1):
        assert sync_bookings_to_clickhouse(full=True) == 1
        assert sync_bookings_to_clickhouse() == 0

    booking.contact_phone = "+8801700000000"
    booking.save(update_fields=["contact_phone", "updated_at"])

    with patch("apps.analytics.tasks.insert_rows", return_value=1):
        assert sync_bookings_to_clickhouse() == 1


def test_a_failed_insert_does_not_advance_the_cursor(booking):
    with patch("apps.analytics.tasks.insert_rows", side_effect=RuntimeError("clickhouse down")):
        assert sync_bookings_to_clickhouse(full=True) == 0

    with patch("apps.analytics.tasks.insert_rows", return_value=1):
        assert sync_bookings_to_clickhouse() == 1


# --- fare snapshot -----------------------------------------------------------


def test_the_daily_rollup_snapshots_the_cheapest_fare(client, make_flight, make_fare):
    flight = make_flight(days_ahead=14, capacity=10, rbd="Y")
    make_fare(rbd="Y", amount="200.00")

    client.post(
        reverse("v1:search-flights"),
        {
            "trip_type": "ONE_WAY",
            "slices": [
                {
                    "origin": "DAC",
                    "destination": "DXB",
                    "date": flight.departure_local.date().isoformat(),
                }
            ],
            "passengers": {"adults": 1, "children": 0, "infants": 0},
            "cabin": "ECONOMY",
            "currency": "USD",
            "max_stops": 0,
        },
        format="json",
    )

    with patch("apps.analytics.tasks.insert_rows", return_value=1) as insert:
        assert rollup_daily_metrics() == 1

    table, rows, columns = insert.call_args.args
    assert table == "wayfare.fare_price_history"

    row = dict(zip(columns, rows[0], strict=True))
    assert (row["origin"], row["destination"]) == ("DAC", "DXB")
    assert row["cheapest_amount"] == Decimal("200.00")


def test_the_rollup_is_quiet_on_a_day_with_no_searches():
    with patch("apps.analytics.tasks.insert_rows") as insert:
        assert rollup_daily_metrics(day="2020-01-01") == 0
    insert.assert_not_called()


def test_a_report_is_a_plain_dataclass():
    report = Report(columns=["a"], rows=[[1], [2]])
    assert report.as_dict() == {"columns": ["a"], "rows": [[1], [2]], "row_count": 2}
