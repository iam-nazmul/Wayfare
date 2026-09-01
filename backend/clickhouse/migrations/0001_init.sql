-- Raw clickstream. Deduplicable by event_id; TTL bounds growth.
CREATE TABLE IF NOT EXISTS wayfare.events
(
    event_id      UUID,
    event_time    DateTime64(3, 'UTC'),
    event_name    LowCardinality(String),
    session_id    String,
    anon_id       String,
    user_id       Nullable(UInt64),
    page_path     String,
    referrer      String,
    origin        LowCardinality(String),
    destination   LowCardinality(String),
    cabin         LowCardinality(String),
    pax_count     UInt8,
    amount        Decimal(12, 2),
    currency      LowCardinality(String),
    duration_ms   UInt32,
    props         String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_name, event_time, session_id)
TTL toDateTime(event_time) + INTERVAL 400 DAY
SETTINGS index_granularity = 8192;

-- One row per executed search.
CREATE TABLE IF NOT EXISTS wayfare.search_log
(
    search_id       UUID,
    event_time      DateTime64(3, 'UTC'),
    session_id      String,
    user_id         Nullable(UInt64),
    origin          LowCardinality(String),
    destination     LowCardinality(String),
    depart_date     Date,
    return_date     Nullable(Date),
    trip_type       LowCardinality(String),
    pax_adults      UInt8,
    pax_children    UInt8,
    pax_infants     UInt8,
    cabin           LowCardinality(String),
    currency        LowCardinality(String),
    results_count   UInt16,
    cheapest_amount Decimal(12, 2),
    median_amount   Decimal(12, 2),
    cache_hit       UInt8,
    latency_ms      UInt32,
    partial         UInt8
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (origin, destination, depart_date, event_time)
TTL toDateTime(event_time) + INTERVAL 400 DAY;

-- HTTP access log.
CREATE TABLE IF NOT EXISTS wayfare.api_request_log
(
    request_id  String,
    ts          DateTime64(3, 'UTC'),
    method      LowCardinality(String),
    path        String,
    route       LowCardinality(String),
    status      UInt16,
    duration_ms UInt32,
    user_id     Nullable(UInt64),
    ip          String,
    user_agent  String,
    error_code  LowCardinality(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (route, ts)
TTL toDateTime(ts) + INTERVAL 90 DAY;

-- Application logs.
CREATE TABLE IF NOT EXISTS wayfare.app_log
(
    ts         DateTime64(3, 'UTC'),
    level      LowCardinality(String),
    logger     LowCardinality(String),
    service    LowCardinality(String),
    message    String,
    request_id String,
    trace_id   String,
    user_id    Nullable(UInt64),
    task_name  LowCardinality(String),
    exception  String,
    extra      String
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (level, service, ts)
TTL toDateTime(ts) + INTERVAL 30 DAY;

-- Booking mirror, replicated from Postgres. Dedup by booking_id, newest updated_at wins.
CREATE TABLE IF NOT EXISTS wayfare.bookings_mirror
(
    booking_id       UInt64,
    pnr              String,
    status           LowCardinality(String),
    user_id          Nullable(UInt64),
    agency_id        Nullable(UInt64),
    origin           LowCardinality(String),
    destination      LowCardinality(String),
    trip_type        LowCardinality(String),
    cabin            LowCardinality(String),
    pax_count        UInt8,
    base_amount      Decimal(12, 2),
    tax_amount       Decimal(12, 2),
    ancillary_amount Decimal(12, 2),
    total_amount     Decimal(12, 2),
    total_amount_usd Decimal(12, 2),
    currency         LowCardinality(String),
    source_channel   LowCardinality(String),
    booked_at        DateTime('UTC'),
    departure_at     DateTime('UTC'),
    updated_at       DateTime('UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(booked_at)
ORDER BY (booking_id);

-- Fare price history, for trend charts and fare alerts.
CREATE TABLE IF NOT EXISTS wayfare.fare_price_history
(
    captured_at     DateTime('UTC'),
    origin          LowCardinality(String),
    destination     LowCardinality(String),
    depart_date     Date,
    cabin           LowCardinality(String),
    cheapest_amount Decimal(12, 2),
    currency        LowCardinality(String),
    seats_remaining UInt16
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(captured_at)
ORDER BY (origin, destination, depart_date, captured_at)
TTL captured_at + INTERVAL 2 YEAR;
