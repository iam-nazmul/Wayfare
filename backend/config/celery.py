import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("wayfare")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.task_routes = {
    "payments.*": {"queue": "critical"},
    "ticketing.*": {"queue": "critical"},
    "booking.release_expired_holds": {"queue": "critical"},
    "booking.*": {"queue": "default"},
    "inventory.*": {"queue": "default"},
    "pricing.*": {"queue": "default"},
    "ops.relay_outbox": {"queue": "default"},
    "ops.*": {"queue": "default"},
    "notifications.*": {"queue": "notifications"},
    "analytics.*": {"queue": "analytics"},
    "maintenance.*": {"queue": "maintenance"},
}

app.conf.beat_schedule = {
    "release-expired-holds": {
        "task": "booking.release_expired_holds",
        "schedule": 60.0,
    },
    "expire-offers": {
        "task": "booking.expire_offers",
        "schedule": 300.0,
    },
    "relay-outbox": {
        "task": "ops.relay_outbox",
        "schedule": 5.0,
    },
    "reconcile-pending-payments": {
        "task": "payments.reconcile_pending_payments",
        "schedule": 300.0,
    },
    "void-expired-unticketed": {
        "task": "ticketing.void_expired_unticketed",
        "schedule": 900.0,
    },
    "mark-departed-flights": {
        "task": "inventory.mark_departed_flights",
        "schedule": 600.0,
    },
    "detect-disruptions": {
        "task": "ops.detect_disruptions",
        "schedule": 300.0,
    },
    "flush-event-buffer": {
        "task": "analytics.flush_event_buffer",
        "schedule": 5.0,
    },
    "sync-bookings-to-clickhouse": {
        "task": "analytics.sync_bookings_to_clickhouse",
        "schedule": 300.0,
    },
    "send-departure-reminders": {
        "task": "notifications.send_departure_reminders",
        "schedule": crontab(minute=5),
    },
    "send-checkin-open": {
        "task": "notifications.send_checkin_open",
        "schedule": crontab(minute=15),
    },
    "materialise-schedules": {
        "task": "inventory.materialise_schedules",
        "schedule": crontab(hour=2, minute=0),
    },
    "rollup-daily-metrics": {
        "task": "analytics.rollup_daily_metrics",
        "schedule": crontab(hour=1, minute=0),
    },
    "refresh-exchange-rates": {
        "task": "pricing.refresh_exchange_rates",
        "schedule": crontab(hour=3, minute=0),
    },
    "rebuild-calendar-cache": {
        "task": "pricing.rebuild_calendar_cache",
        "schedule": crontab(hour=4, minute=0),
    },
    "purge-expired-idempotency-keys": {
        "task": "maintenance.purge_expired_idempotency_keys",
        "schedule": crontab(hour=5, minute=0),
    },
}
