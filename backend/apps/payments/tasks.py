import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.booking.constants import BookingStatus
from apps.common.locks import LockNotAcquired, redis_lock
from apps.common.money import Money
from apps.ticketing.tasks import exchange_tickets, issue_tickets

from .constants import RECONCILE_AFTER_SECONDS, IntentStatus
from .models import PaymentIntent, ProviderWebhookEvent, Refund
from .services.confirm import apply_failed_payment, apply_successful_payment

logger = logging.getLogger("wayfare.payments")

SUCCESS_EVENTS = {"payment_intent.succeeded"}
FAILURE_EVENTS = {"payment_intent.payment_failed"}


@shared_task(
    name="payments.handle_payment_succeeded",
    queue="critical",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def handle_payment_succeeded(event_id: int) -> str:
    """Apply one provider callback to the booking it belongs to.

    Money-touching, so it takes the booking lock *and* re-reads state inside the transaction.
    The lock only reduces contention; `apply_successful_payment` is idempotent on the charge id,
    which is what actually makes a redelivered webhook safe.
    """
    event = ProviderWebhookEvent.objects.filter(pk=event_id).first()
    if event is None or event.processed_at is not None:
        return "skipped"

    intent = PaymentIntent.objects.filter(
        provider_intent_id=event.payload.get("intent_id", "")
    ).select_related("booking").first()

    if intent is None:
        _mark(event, error="No intent matches this event.")
        logger.warning("webhook_without_intent", extra={"event_id": event.provider_event_id})
        return "orphan"

    try:
        with redis_lock(f"booking:{intent.booking.pnr}", timeout=60):
            outcome = _apply(event, intent)
    except LockNotAcquired:
        logger.info("payment_lock_busy", extra={"pnr": intent.booking.pnr})
        raise

    _mark(event)

    # Dispatched only after the lock is released: issuing takes the same booking lock, and the
    # payment is already committed by here, so a lost dispatch is recoverable rather than a
    # rolled-back charge. `void_expired_unticketed` is what notices if this never lands.
    if outcome == "captured":
        issue_tickets.delay(intent.booking_id)
    elif outcome == "exchanged":
        exchange_tickets.delay(intent.booking_id)

    return outcome


def _apply(event: ProviderWebhookEvent, intent: PaymentIntent) -> str:
    payload = event.payload

    if event.event_type in FAILURE_EVENTS:
        apply_failed_payment(
            intent,
            charge_id=payload.get("charge_id", f"failed:{event.provider_event_id}"),
            code=payload.get("failure_code", ""),
            message=payload.get("failure_message", ""),
        )
        PaymentIntent.objects.filter(pk=intent.pk).update(status=IntentStatus.FAILED)
        return "failed"

    if event.event_type not in SUCCESS_EVENTS:
        return "ignored"

    apply_successful_payment(
        intent,
        charge_id=payload["charge_id"],
        amount=Decimal(str(payload.get("amount", intent.amount))),
        card_brand=payload.get("card_brand", ""),
        card_last4=payload.get("card_last4", ""),
    )
    PaymentIntent.objects.filter(pk=intent.pk).update(status=IntentStatus.SUCCEEDED)

    # What follows depends on why they were paying: a first sale needs tickets, an exchange
    # needs the reissue.
    intent.booking.refresh_from_db()
    if intent.booking.status == BookingStatus.CHANGE_PENDING:
        return "exchanged"
    return "captured"


def _mark(event: ProviderWebhookEvent, error: str = "") -> None:
    ProviderWebhookEvent.objects.filter(pk=event.pk).update(
        processed_at=timezone.now() if not error else None,
        attempts=event.attempts + 1,
        last_error=error,
    )


@shared_task(name="payments.reconcile_pending_payments", queue="critical", acks_late=True)
def reconcile_pending_payments(batch: int = 200) -> int:
    """Confirmation must not depend on a webhook being delivered *and* processed.

    Two things go wrong after a traveller pays: the callback never arrives, or it arrives and
    its task is lost. This picks up the second — every verified event still unprocessed after
    the grace window is re-dispatched, which the handler's idempotency makes safe.

    A real PSP implementation also polls the provider for intents with no event at all. The
    sandbox has no state of its own to poll, so those are counted and logged instead.
    """
    cutoff = timezone.now() - timedelta(seconds=RECONCILE_AFTER_SECONDS)

    stranded = list(
        ProviderWebhookEvent.objects.filter(
            processed_at__isnull=True, signature_verified=True, created_at__lt=cutoff
        ).values_list("id", flat=True)[:batch]
    )
    for event_id in stranded:
        handle_payment_succeeded.delay(event_id)

    awaiting = PaymentIntent.objects.filter(
        status__in=[
            IntentStatus.REQUIRES_PAYMENT,
            IntentStatus.REQUIRES_ACTION,
            IntentStatus.PROCESSING,
        ],
        created_at__lt=cutoff,
        booking__status=BookingStatus.HELD,
    ).count()

    if stranded or awaiting:
        logger.warning(
            "payments_reconciled",
            extra={"redispatched": len(stranded), "awaiting": awaiting},
        )

    return len(stranded)


@shared_task(
    name="payments.process_refund",
    queue="critical",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def process_refund(refund_id: int) -> str:
    """Send an approved refund to the provider and close out the booking.

    Money-touching, so it takes the booking lock and re-reads the refund inside the
    transaction: an approval clicked twice must pay out once.
    """
    refund = Refund.objects.select_related("booking", "payment").filter(pk=refund_id).first()
    if refund is None:
        return "missing"

    try:
        with redis_lock(f"booking:{refund.booking.pnr}", timeout=60):
            return _process(refund_id)
    except LockNotAcquired:
        logger.info("refund_lock_busy", extra={"pnr": refund.booking.pnr})
        raise


@transaction.atomic
def _process(refund_id: int) -> str:
    from apps.booking.constants import BookingStatus
    from apps.booking.services.state import transition
    from apps.ops.services.outbox import emit
    from apps.ticketing.services.refund import refund_coupons

    from .constants import LedgerEntryType, RefundStatus
    from .providers import get_provider
    from .services.ledger import post

    # `of=("self",)`: payment is a nullable FK, and Postgres refuses FOR UPDATE on the nullable
    # side of an outer join. The refund row is the one that must not be actioned twice anyway.
    refund = (
        Refund.objects.select_for_update(of=("self",))
        .select_related("booking", "payment")
        .get(pk=refund_id)
    )

    if refund.status != RefundStatus.APPROVED:
        return "skipped"

    provider = get_provider()
    charge_id = refund.payment.provider_charge_id if refund.payment else ""
    result = provider.refund(
        charge_id,
        Money(Decimal(refund.amount), refund.currency),
        idempotency_key=f"refund:{refund.public_id}",
    )

    Refund.objects.filter(pk=refund.pk).update(
        status=RefundStatus.PROCESSED,
        provider_refund_id=result.refund_id,
        processed_at=timezone.now(),
    )

    booking = refund.booking
    post(
        booking,
        LedgerEntryType.REFUND,
        debit=Decimal(refund.amount),
        reference=result.refund_id,
    )
    if refund.penalty_amount:
        post(
            booking,
            LedgerEntryType.PENALTY,
            credit=Decimal(refund.penalty_amount),
            reference=f"penalty:{refund.public_id}",
        )

    refund_coupons(booking)

    if booking.status == BookingStatus.REFUND_PENDING:
        transition(booking, BookingStatus.REFUNDED, reason="refund processed")

    emit(
        "refund",
        str(refund.public_id),
        "refund_processed",
        {
            "refund_id": str(refund.public_id),
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "amount": {"amount": str(refund.amount), "currency": refund.currency},
        },
    )

    logger.info(
        "refund_processed",
        extra={"pnr": booking.pnr, "amount": str(refund.amount)},
    )
    return "processed"
