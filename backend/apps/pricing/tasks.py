import logging
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import ExchangeRate

logger = logging.getLogger("wayfare.pricing")


@shared_task(name="pricing.refresh_exchange_rates", queue="maintenance")
def refresh_exchange_rates() -> int:
    """Carry forward the latest known rate to today.

    A real deployment swaps the body for a provider call. Rates are dated and never overwritten,
    so re-running on a day already covered is a no-op.
    """
    today = timezone.now().date()
    pairs = (
        ExchangeRate.objects.values_list("base", "quote")
        .order_by("base", "quote")
        .distinct()
    )

    created = 0
    for base, quote in pairs:
        latest = (
            ExchangeRate.objects.filter(base=base, quote=quote)
            .order_by("-valid_from")
            .first()
        )
        if latest is None or latest.valid_from >= today:
            continue
        ExchangeRate.objects.get_or_create(
            base=base,
            quote=quote,
            valid_from=today,
            defaults={"rate": latest.rate, "source": "carry-forward"},
        )
        created += 1

    logger.info("exchange_rates_refreshed", extra={"pairs": created})
    return created


@shared_task(name="pricing.rebuild_calendar_cache", queue="default")
def rebuild_calendar_cache() -> int:
    """Drop cached fare calendars so the next viewer rebuilds from current offers."""
    months = 3
    today = timezone.now().date()
    cleared = 0

    delete_pattern = getattr(cache, "delete_pattern", None)
    if delete_pattern is None:
        logger.info("calendar_cache_skip", extra={"reason": "backend has no delete_pattern"})
        return 0

    for offset in range(months):
        month = (today.replace(day=1) + timedelta(days=32 * offset)).strftime("%Y-%m")
        delete_pattern(f"wf:calendar:*:{month}")
        cleared += 1

    return cleared
