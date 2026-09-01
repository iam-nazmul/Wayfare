from contextlib import contextmanager

import redis
from django.conf import settings

_client: redis.Redis | None = None


def lock_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_LOCK_URL, decode_responses=True)
    return _client


class LockNotAcquired(RuntimeError):
    pass


@contextmanager
def redis_lock(key: str, timeout: int = 60, blocking_timeout: int = 10):
    """Advisory lock that reduces contention.

    It is NOT the correctness guarantee — the caller must still re-read the row under
    ``select_for_update`` inside the transaction (CLAUDE.md invariant 3).
    """
    lock = lock_client().lock(key, timeout=timeout, blocking_timeout=blocking_timeout)
    if not lock.acquire():
        raise LockNotAcquired(key)
    try:
        yield
    finally:
        try:
            lock.release()
        except redis.exceptions.LockError:
            pass
