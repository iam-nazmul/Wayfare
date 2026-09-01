import os
import time
import uuid

_LAST_MS = 0
_SEQ = 0


def uuid7() -> uuid.UUID:
    """Time-ordered UUID (RFC 9562 v7): 48-bit ms timestamp, 12-bit counter, 62 random bits.

    The counter keeps ids monotonic within a millisecond so index inserts stay append-only
    under burst load.
    """
    global _LAST_MS, _SEQ

    ms = int(time.time() * 1000)
    if ms == _LAST_MS:
        _SEQ = (_SEQ + 1) & 0x0FFF
    else:
        _LAST_MS, _SEQ = ms, 0

    rand = os.urandom(8)
    value = (
        (ms & 0xFFFF_FFFF_FFFF) << 80
        | 0x7 << 76
        | _SEQ << 64
        | (0b10 << 62)
        | (int.from_bytes(rand, "big") & ((1 << 62) - 1))
    )
    return uuid.UUID(int=value)
