import re

from django.core.exceptions import ImproperlyConfigured
from rest_framework.throttling import ScopedRateThrottle

_RATE = re.compile(r"^(?P<num>\d+)/(?P<count>\d*)(?P<unit>[a-z]+)$")

_SECONDS = {
    "s": 1, "sec": 1, "second": 1,
    "m": 60, "min": 60, "minute": 60,
    "h": 3600, "hour": 3600,
    "d": 86400, "day": 86400,
}


class ScopedWindowRateThrottle(ScopedRateThrottle):
    """``ScopedRateThrottle`` that also understands a multi-unit window.

    DRF reads only the first letter of the period, so ``5/15min`` parses as ``5/1 second``
    — or raises. SPEC.md §7.4 asks for 15-minute windows on login and guest retrieval, so the
    rate string has to carry the count.
    """

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)

        match = _RATE.match(str(rate).strip().lower())
        if match is None:
            raise ImproperlyConfigured(f"Throttle rate {rate!r} is not <num>/<count><unit>.")

        seconds = _SECONDS.get(match["unit"])
        if seconds is None:
            raise ImproperlyConfigured(f"Throttle rate {rate!r} has an unknown period.")

        return int(match["num"]), int(match["count"] or 1) * seconds
