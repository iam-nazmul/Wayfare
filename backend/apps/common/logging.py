import json
import logging
from datetime import UTC, datetime

REDACT = {
    "password",
    "token",
    "authorization",
    "card",
    "cvv",
    "pan",
    "doc_number",
    "secret",
    "client_secret",
}

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


def _redact(key: str, value: object) -> object:
    return "[redacted]" if any(marker in key.lower() for marker in REDACT) else value


class JSONFormatter(logging.Formatter):
    """One JSON object per line. PII is dropped by allowlist, never by hoping nobody logs it."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = _redact(key, value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
