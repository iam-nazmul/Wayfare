import os

from django.db import connection
from django.http import HttpRequest, JsonResponse

from .locks import lock_client


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness: the process is up. No dependency checks — never fail a rolling deploy on Redis."""
    return JsonResponse({"status": "ok"})


def readyz(_request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 — report, never raise, from a probe
        checks["postgres"] = f"error: {exc}"

    try:
        lock_client().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    try:
        from apps.analytics.clickhouse import ping as ch_ping

        ch_ping()
        checks["clickhouse"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["clickhouse"] = f"error: {exc}"

    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse({"status": "ok" if healthy else "degraded", "checks": checks},
                        status=200 if healthy else 503)


def version(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "version": os.environ.get("APP_VERSION", "dev"),
            "commit": os.environ.get("GIT_SHA", "unknown"),
        }
    )
