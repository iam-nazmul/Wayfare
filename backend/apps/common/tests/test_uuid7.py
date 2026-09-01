from apps.common.uuid7 import uuid7


def test_version_and_variant_bits():
    value = uuid7()
    assert value.version == 7
    assert (value.int >> 62) & 0b11 == 0b10


def test_ids_are_unique():
    assert len({uuid7() for _ in range(5_000)}) == 5_000


def test_ids_are_time_ordered():
    """Index inserts stay append-only only if ids increase within a millisecond."""
    values = [uuid7() for _ in range(1_000)]
    assert values == sorted(values)
