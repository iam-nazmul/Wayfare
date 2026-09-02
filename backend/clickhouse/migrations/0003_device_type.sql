-- The funnel is reported by device (SPEC.md §9.5), but `events` had no column for it and the
-- rollup wrote a constant empty string. Add the column and rebuild the view over it.
ALTER TABLE wayfare.events
    ADD COLUMN IF NOT EXISTS device_type LowCardinality(String) DEFAULT '' AFTER referrer;

DROP TABLE IF EXISTS wayfare.funnel_daily_mv;

CREATE MATERIALIZED VIEW IF NOT EXISTS wayfare.funnel_daily_mv
TO wayfare.funnel_daily AS
SELECT
    toDate(event_time)      AS day,
    event_name              AS step,
    device_type,
    uniqState(session_id)   AS sessions,
    countState()            AS events
FROM wayfare.events
WHERE event_name IN ('page_view', 'search_submitted', 'offer_selected',
                     'pax_details_completed', 'payment_started', 'booking_confirmed')
GROUP BY day, step, device_type;
