-- Funnel rollup: read this, never raw events, for conversion reporting.
CREATE TABLE IF NOT EXISTS wayfare.funnel_daily
(
    day         Date,
    step        LowCardinality(String),
    device_type LowCardinality(String),
    sessions    AggregateFunction(uniq, String),
    events      AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (day, step, device_type);

CREATE MATERIALIZED VIEW IF NOT EXISTS wayfare.funnel_daily_mv
TO wayfare.funnel_daily AS
SELECT
    toDate(event_time)      AS day,
    event_name              AS step,
    ''                      AS device_type,
    uniqState(session_id)   AS sessions,
    countState()            AS events
FROM wayfare.events
WHERE event_name IN ('page_view', 'search_submitted', 'offer_selected',
                     'pax_details_completed', 'payment_started', 'booking_confirmed')
GROUP BY day, step, device_type;

-- Route demand rollup.
CREATE TABLE IF NOT EXISTS wayfare.route_demand_daily
(
    day             Date,
    origin          LowCardinality(String),
    destination     LowCardinality(String),
    searches        AggregateFunction(count),
    unique_sessions AggregateFunction(uniq, String),
    avg_cheapest    AggregateFunction(avg, Decimal(12, 2))
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (day, origin, destination);

CREATE MATERIALIZED VIEW IF NOT EXISTS wayfare.route_demand_daily_mv
TO wayfare.route_demand_daily AS
SELECT
    toDate(event_time)           AS day,
    origin,
    destination,
    countState()                 AS searches,
    uniqState(session_id)        AS unique_sessions,
    avgState(cheapest_amount)    AS avg_cheapest
FROM wayfare.search_log
GROUP BY day, origin, destination;
