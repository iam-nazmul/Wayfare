from decimal import Decimal

from ..constants import LedgerEntryType
from ..models import LedgerEntry


def balance(booking) -> Decimal:
    last = booking.ledger_entries.order_by("created_at").last()
    return Decimal(last.balance_after) if last else Decimal("0.00")


def post(
    booking,
    entry_type: str,
    *,
    debit: Decimal = Decimal("0.00"),
    credit: Decimal = Decimal("0.00"),
    reference: str = "",
) -> LedgerEntry:
    """Append one movement and carry the running balance forward.

    Append-only: entries are never updated, so the balance is always re-derivable by replaying
    the rows in order.
    """
    return LedgerEntry.objects.create(
        booking=booking,
        entry_type=entry_type,
        debit=debit,
        credit=credit,
        currency=booking.currency,
        balance_after=balance(booking) + debit - credit,
        reference=reference,
    )


def post_reprice(booking, difference: Decimal, reference: str = "") -> LedgerEntry | None:
    """Record that an exchange changed what the booking owes.

    Without this the delta payment credits a balance nothing ever debited, and the ledger ends
    up negative on every exchange.
    """
    if difference == 0:
        return None

    return post(
        booking,
        LedgerEntryType.ADJUSTMENT,
        debit=difference if difference > 0 else Decimal("0.00"),
        credit=-difference if difference < 0 else Decimal("0.00"),
        reference=reference or f"reprice:{booking.pnr}",
    )
