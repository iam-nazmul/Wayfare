import secrets

from django.db import IntegrityError, transaction

from ..constants import PNR_ALPHABET, PNR_LENGTH, PNR_MAX_ATTEMPTS
from ..models import Booking


class PnrExhausted(RuntimeError):
    """Five collisions in a row means the keyspace or the RNG is wrong, not bad luck."""


def new_pnr() -> str:
    return "".join(secrets.choice(PNR_ALPHABET) for _ in range(PNR_LENGTH))


def create_with_pnr(**fields) -> Booking:
    """Create a booking, retrying on the unique violation rather than pre-checking.

    A SELECT-then-INSERT would still race; letting the unique index arbitrate is the only
    check that holds under concurrency.
    """
    for _ in range(PNR_MAX_ATTEMPTS):
        try:
            with transaction.atomic():
                return Booking.objects.create(pnr=new_pnr(), **fields)
        except IntegrityError as exc:
            if "pnr" not in str(exc):
                raise
            continue

    raise PnrExhausted(f"No free PNR after {PNR_MAX_ATTEMPTS} attempts.")
