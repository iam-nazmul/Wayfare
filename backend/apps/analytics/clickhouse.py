import logging
from collections.abc import Sequence
from typing import Any

from django.conf import settings

logger = logging.getLogger("wayfare.analytics")

_client: Any = None


def get_client():
    """Lazy singleton. ClickHouse is optional at import time — nothing may fail on it."""
    global _client
    if _client is None:
        import clickhouse_connect

        conf = settings.CLICKHOUSE
        _client = clickhouse_connect.get_client(
            host=conf["HOST"],
            port=conf["PORT"],
            database=conf["DATABASE"],
            username=conf["USER"],
            password=conf["PASSWORD"],
            connect_timeout=5,
            send_receive_timeout=30,
        )
    return _client


def reset_client() -> None:
    global _client
    _client = None


def ping() -> bool:
    get_client().query("SELECT 1")
    return True


def insert_rows(
    table: str, rows: Sequence[Sequence[Any]], column_names: list[str],
    column_types: list[str] | None = None,
) -> int:
    """Batch insert. ``column_types`` skips the server DESCRIBE round-trip on hot paths."""
    if not rows:
        return 0

    conf = settings.CLICKHOUSE
    ch_settings = {}
    if conf["ASYNC_INSERT"]:
        ch_settings = {"async_insert": 1, "wait_for_async_insert": 0}

    summary = get_client().insert(
        table,
        rows,
        column_names=column_names,
        column_type_names=column_types,
        settings=ch_settings,
    )
    return getattr(summary, "written_rows", len(rows))


def query(sql: str, parameters: dict[str, Any] | None = None) -> list[tuple]:
    """Parameterised only. Interpolating into ClickHouse SQL is treated as SQL injection."""
    return get_client().query(sql, parameters=parameters or {}).result_rows
