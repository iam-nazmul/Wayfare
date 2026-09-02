"""The `/ops/reports/*` catalogue (SPEC.md §9.5).

Every query is parameterised — interpolating a date or a route into ClickHouse SQL is treated as
SQL injection (CLAUDE.md invariant 10). Reports read materialised views wherever a rollup exists
and fall back to the raw tables only where one does not.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .clickhouse import query

#: Conversion order, so the funnel renders as a funnel rather than alphabetically.
FUNNEL_STEPS = [
    "page_view",
    "search_submitted",
    "offer_selected",
    "pax_details_completed",
    "payment_started",
    "booking_confirmed",
]

#: Statuses that represent money actually earned.
SOLD_STATUSES = ["TICKETED", "CONFIRMED", "PENDING_TICKETING"]


@dataclass(frozen=True, slots=True)
class Report:
    columns: list[str]
    rows: list[list]

    def as_dict(self) -> dict:
        return {
            "columns": self.columns,
            "rows": [list(row) for row in self.rows],
            "row_count": len(self.rows),
        }


def _window(date_from: date, date_to: date) -> dict:
    return {"date_from": date_from, "date_to": date_to}


def funnel(date_from: date, date_to: date, **filters) -> Report:
    """Step-by-step conversion from the pre-aggregated rollup, never the raw events."""
    rows = query(
        """
        SELECT step,
               device_type,
               uniqMerge(sessions) AS sessions,
               countMerge(events)  AS events
        FROM wayfare.funnel_daily
        WHERE day BETWEEN %(date_from)s AND %(date_to)s
        GROUP BY step, device_type
        ORDER BY sessions DESC
        """,
        _window(date_from, date_to),
    )

    order = {step: index for index, step in enumerate(FUNNEL_STEPS)}
    ranked = sorted(rows, key=lambda row: (order.get(row[0], len(order)), row[1]))
    return Report(["step", "device_type", "sessions", "events"], ranked)


def search_conversion(date_from: date, date_to: date, **filters) -> Report:
    """Look-to-book by route: searches against bookings that actually sold."""
    rows = query(
        """
        SELECT s.origin      AS origin,
               s.destination AS destination,
               s.searches    AS searches,
               b.bookings    AS bookings,
               round(b.bookings / nullIf(s.searches, 0) * 100, 2) AS conversion_pct
        FROM (
            SELECT origin, destination, count() AS searches
            FROM wayfare.search_log
            WHERE toDate(event_time) BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY origin, destination
        ) AS s
        LEFT JOIN (
            SELECT origin, destination, count() AS bookings
            FROM wayfare.bookings_mirror FINAL
            WHERE toDate(booked_at) BETWEEN %(date_from)s AND %(date_to)s
              AND status IN %(sold)s
            GROUP BY origin, destination
        ) AS b USING (origin, destination)
        ORDER BY searches DESC
        LIMIT 200
        """,
        {**_window(date_from, date_to), "sold": SOLD_STATUSES},
    )
    return Report(
        ["origin", "destination", "searches", "bookings", "conversion_pct"], rows
    )


def revenue(date_from: date, date_to: date, **filters) -> Report:
    """Revenue by day, route, cabin and channel, normalised to USD at sale time."""
    rows = query(
        """
        SELECT toDate(booked_at) AS day,
               origin,
               destination,
               cabin,
               source_channel,
               count()                AS bookings,
               sum(pax_count)         AS passengers,
               sum(total_amount_usd)  AS revenue_usd
        FROM wayfare.bookings_mirror FINAL
        WHERE toDate(booked_at) BETWEEN %(date_from)s AND %(date_to)s
          AND status IN %(sold)s
        GROUP BY day, origin, destination, cabin, source_channel
        ORDER BY day DESC, revenue_usd DESC
        LIMIT 1000
        """,
        {**_window(date_from, date_to), "sold": SOLD_STATUSES},
    )
    return Report(
        [
            "day", "origin", "destination", "cabin", "source_channel",
            "bookings", "passengers", "revenue_usd",
        ],
        rows,
    )


def load_factor(date_from: date, date_to: date, **filters) -> Report:
    """Seats sold ÷ capacity by flight and departure date.

    Reads Postgres, not the mirror: this is live inventory, and a stale answer here would have
    ops making capacity decisions on yesterday's numbers.
    """
    from django.db.models import F, Sum

    from apps.inventory.models import CabinConfig

    rows = (
        CabinConfig.objects.filter(
            flight__departure_utc__date__gte=date_from,
            flight__departure_utc__date__lte=date_to,
        )
        .values(
            "flight__flight_number",
            "flight__airline_id",
            "flight__origin_airport_id",
            "flight__destination_airport_id",
            "cabin",
        )
        .annotate(
            departure=F("flight__departure_utc"),
            capacity=Sum("capacity"),
            sold=Sum("seats_sold"),
            held=Sum("seats_held"),
        )
        .order_by("departure")[:1000]
    )

    return Report(
        [
            "designator", "origin", "destination", "cabin", "departure",
            "capacity", "sold", "held", "load_factor_pct",
        ],
        [
            [
                f"{row['flight__airline_id']}{row['flight__flight_number']}",
                row["flight__origin_airport_id"],
                row["flight__destination_airport_id"],
                row["cabin"],
                row["departure"],
                row["capacity"],
                row["sold"],
                row["held"],
                round(row["sold"] / row["capacity"] * 100, 2) if row["capacity"] else 0.0,
            ]
            for row in rows
        ],
    )


def top_routes(date_from: date, date_to: date, **filters) -> Report:
    """Demand against sales, from the route-demand rollup."""
    rows = query(
        """
        SELECT origin,
               destination,
               countMerge(searches)        AS searches,
               uniqMerge(unique_sessions)  AS sessions,
               round(avgMerge(avg_cheapest), 2) AS avg_cheapest
        FROM wayfare.route_demand_daily
        WHERE day BETWEEN %(date_from)s AND %(date_to)s
        GROUP BY origin, destination
        ORDER BY searches DESC
        LIMIT 100
        """,
        _window(date_from, date_to),
    )
    return Report(["origin", "destination", "searches", "sessions", "avg_cheapest"], rows)


def abandonment(date_from: date, date_to: date, **filters) -> Report:
    """Sessions that reached payment but never confirmed, with the last error they saw."""
    rows = query(
        """
        SELECT session_id,
               max(event_time)                                   AS last_seen,
               anyLast(page_path)                                AS last_page,
               anyLastIf(props, event_name = 'error_shown')      AS last_error,
               anyLast(device_type)                              AS device_type
        FROM wayfare.events
        WHERE toDate(event_time) BETWEEN %(date_from)s AND %(date_to)s
        GROUP BY session_id
        HAVING countIf(event_name = 'payment_started') > 0
           AND countIf(event_name = 'booking_confirmed') = 0
        ORDER BY last_seen DESC
        LIMIT 500
        """,
        _window(date_from, date_to),
    )
    return Report(
        ["session_id", "last_seen", "last_page", "last_error", "device_type"], rows
    )


def api_health(date_from: date, date_to: date, **filters) -> Report:
    """Latency percentiles and error rate by route — the operational view of the API."""
    rows = query(
        """
        SELECT route,
               count()                                    AS requests,
               round(quantile(0.50)(duration_ms), 1)      AS p50_ms,
               round(quantile(0.95)(duration_ms), 1)      AS p95_ms,
               round(quantile(0.99)(duration_ms), 1)      AS p99_ms,
               countIf(status >= 500)                     AS server_errors,
               countIf(status >= 400 AND status < 500)    AS client_errors,
               round(countIf(status >= 500) / count() * 100, 3) AS error_rate_pct
        FROM wayfare.api_request_log
        WHERE toDate(ts) BETWEEN %(date_from)s AND %(date_to)s
        GROUP BY route
        ORDER BY requests DESC
        LIMIT 200
        """,
        _window(date_from, date_to),
    )
    return Report(
        [
            "route", "requests", "p50_ms", "p95_ms", "p99_ms",
            "server_errors", "client_errors", "error_rate_pct",
        ],
        rows,
    )


def fare_trend(date_from: date, date_to: date, **filters) -> Report:
    """Price movement for a route and departure date."""
    origin = (filters.get("origin") or "").upper()
    destination = (filters.get("destination") or "").upper()

    rows = query(
        """
        SELECT toDate(captured_at) AS day,
               origin,
               destination,
               depart_date,
               cabin,
               min(cheapest_amount) AS cheapest,
               any(currency)        AS currency,
               min(seats_remaining) AS seats_remaining
        FROM wayfare.fare_price_history
        WHERE toDate(captured_at) BETWEEN %(date_from)s AND %(date_to)s
          AND (%(origin)s = '' OR origin = %(origin)s)
          AND (%(destination)s = '' OR destination = %(destination)s)
        GROUP BY day, origin, destination, depart_date, cabin
        ORDER BY day, depart_date
        LIMIT 1000
        """,
        {
            **_window(date_from, date_to),
            "origin": origin,
            "destination": destination,
        },
    )
    return Report(
        [
            "day", "origin", "destination", "depart_date", "cabin",
            "cheapest", "currency", "seats_remaining",
        ],
        rows,
    )


REPORTS: dict[str, Callable[..., Report]] = {
    "funnel": funnel,
    "search-conversion": search_conversion,
    "revenue": revenue,
    "load-factor": load_factor,
    "top-routes": top_routes,
    "abandonment": abandonment,
    "api-health": api_health,
    "fare-trend": fare_trend,
}
