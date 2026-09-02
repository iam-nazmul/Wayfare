import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import DomainError, InvalidTransition
from apps.ops.services.audit import record
from apps.ops.services.outbox import emit
from apps.pricing.services.refunds import RefundQuote

from ..constants import RefundStatus
from ..models import Payment, Refund

logger = logging.getLogger("wayfare.payments")

OPEN_STATUSES = frozenset({RefundStatus.REQUESTED, RefundStatus.APPROVED})


class RefundNotAllowed(DomainError):
    status_code = 409
    code = "refund_not_allowed"
    title = "This refund cannot be actioned"


def auto_approves(amount: Decimal) -> bool:
    """Small refunds go straight through; anything larger is a human's decision."""
    return amount <= Decimal(str(settings.REFUND_AUTO_APPROVE_LIMIT))


@transaction.atomic
def request_refund(booking, quote: RefundQuote, *, actor=None, reason: str = "") -> Refund:
    """Open a refund for a cancelled booking, approving it if it is small enough.

    One open refund per booking: a second cancel request must not queue a second payout.
    """
    existing = booking.refunds.filter(status__in=OPEN_STATUSES).first()
    if existing is not None:
        return existing

    payment = (
        Payment.objects.filter(booking=booking, status="CAPTURED").order_by("-created_at").first()
    )

    refund = Refund.objects.create(
        booking=booking,
        payment=payment,
        amount=quote.refundable.amount,
        currency=quote.currency,
        status=RefundStatus.REQUESTED,
        reason=reason or quote.reason,
        requested_by=actor if actor is not None and actor.is_authenticated else None,
        penalty_amount=quote.penalty.amount,
        refundable_amount=quote.refundable.amount,
    )

    if auto_approves(refund.amount):
        approve(refund, actor=None, note="under the auto-approval limit")
    else:
        emit(
            "refund",
            str(refund.public_id),
            "refund_requested",
            {
                "refund_id": str(refund.public_id),
                "pnr": booking.pnr,
                "amount": {"amount": str(refund.amount), "currency": refund.currency},
            },
        )
        logger.info(
            "refund_queued", extra={"pnr": booking.pnr, "amount": str(refund.amount)}
        )

    refund.refresh_from_db()
    return refund


@transaction.atomic
def approve(refund: Refund, *, actor=None, note: str = "") -> Refund:
    """Release a refund to the provider. The money moves in ``payments.process_refund``."""
    if refund.status != RefundStatus.REQUESTED:
        raise RefundNotAllowed(f"A {refund.status} refund cannot be approved.")

    Refund.objects.filter(pk=refund.pk, status=RefundStatus.REQUESTED).update(
        status=RefundStatus.APPROVED,
        approved_by=actor if actor is not None and actor.is_authenticated else None,
    )
    refund.refresh_from_db()

    record(
        "refund.approved",
        "refund",
        str(refund.public_id),
        actor=actor,
        before={"status": RefundStatus.REQUESTED},
        after={"status": RefundStatus.APPROVED},
        reason=note,
    )

    from ..tasks import process_refund

    transaction.on_commit(lambda: process_refund.delay(refund.id))
    return refund


@transaction.atomic
def reject(refund: Refund, *, actor=None, reason: str = "") -> Refund:
    """Decline a refund. The booking stays cancelled — the money simply is not returned."""
    if refund.status != RefundStatus.REQUESTED:
        raise RefundNotAllowed(f"A {refund.status} refund cannot be rejected.")

    Refund.objects.filter(pk=refund.pk, status=RefundStatus.REQUESTED).update(
        status=RefundStatus.REJECTED,
        approved_by=actor if actor is not None and actor.is_authenticated else None,
        reason=reason or refund.reason,
        processed_at=timezone.now(),
    )
    refund.refresh_from_db()

    record(
        "refund.rejected",
        "refund",
        str(refund.public_id),
        actor=actor,
        before={"status": RefundStatus.REQUESTED},
        after={"status": RefundStatus.REJECTED},
        reason=reason,
    )

    emit(
        "refund",
        str(refund.public_id),
        "refund_rejected",
        {
            "refund_id": str(refund.public_id),
            "pnr": refund.booking.pnr,
            "contact_email": refund.booking.contact_email,
            "reason": reason,
        },
    )
    return refund


def guard_transition(booking, to_status: str) -> None:
    """Raise the domain error rather than letting an illegal move surface as a 500."""
    from apps.booking.services.state import can_transition

    if not can_transition(booking.status, to_status):
        raise InvalidTransition(f"A booking cannot go from {booking.status} to {to_status}.")
