import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.booking.constants import BookingStatus, SegmentStatus
from apps.booking.models import Booking
from apps.booking.services.state import transition
from apps.inventory.services.availability import SeatRequest
from apps.inventory.services.availability import confirm as confirm_seats
from apps.ops.services.outbox import emit

from ..constants import LedgerEntryType, PaymentStatus, RefundStatus
from ..models import Payment, PaymentIntent, Refund
from .ledger import post

logger = logging.getLogger("wayfare.payments")


@transaction.atomic
def apply_successful_payment(
    intent: PaymentIntent,
    *,
    charge_id: str,
    amount: Decimal,
    card_brand: str = "",
    card_last4: str = "",
) -> Payment:
    """Record the money, turn the held seats into sales, and move the booking forward.

    Idempotent on ``charge_id``: the provider will deliver the same success more than once, and
    the second delivery must not sell the seats twice. Everything here is one transaction — a
    payment recorded without its inventory movement would oversell the flight.
    """
    existing = Payment.objects.filter(provider_charge_id=charge_id).first()
    if existing is not None:
        logger.info("payment_already_applied", extra={"charge_id": charge_id})
        return existing

    booking = Booking.objects.select_for_update().get(pk=intent.booking_id)

    payment = Payment.objects.create(
        booking=booking,
        intent=intent,
        provider=intent.provider,
        provider_charge_id=charge_id,
        amount=amount,
        currency=intent.currency,
        status=PaymentStatus.CAPTURED,
        card_brand=card_brand,
        card_last4=card_last4,
        authorised_at=timezone.now(),
        captured_at=timezone.now(),
    )

    # The money moved at the provider whatever state we are in, so it is recorded either way.
    Booking.objects.filter(pk=booking.pk).update(paid_amount=F("paid_amount") + amount)
    booking.refresh_from_db()
    _post_ledger(booking, payment)

    if booking.status == BookingStatus.CHANGE_PENDING:
        # Paying the difference on an exchange. The new seats were held when the change was
        # confirmed; capture turns them into sales, and the reissue follows outside the lock.
        _settle_holds(booking)
        logger.info(
            "change_delta_captured",
            extra={"pnr": booking.pnr, "amount": str(amount)},
        )
        return payment

    if booking.status != BookingStatus.HELD:
        # The hold expired or the booking was cancelled while the callback was in flight. The
        # seats are gone and must not be re-taken, so the only honest outcome is to give the
        # money back rather than leave a paid booking with nothing behind it.
        _request_refund(booking, payment)
        return payment

    _settle_holds(booking)
    booking.segments.update(status=SegmentStatus.CONFIRMED)
    Booking.objects.filter(pk=booking.pk).update(hold_expires_at=None)
    booking.refresh_from_db()

    transition(booking, BookingStatus.PENDING_TICKETING, reason="payment captured")
    emit(
        "booking",
        booking.pnr,
        "booking_confirmed",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "paid": {"amount": str(amount), "currency": booking.currency},
        },
    )

    logger.info(
        "payment_captured",
        extra={"pnr": booking.pnr, "amount": str(amount), "charge_id": charge_id},
    )
    return payment


def _settle_holds(booking: Booking) -> int:
    """Turn every live hold on a booking into a sale."""
    holds = list(booking.holds.filter(released_at__isnull=True))
    if not holds:
        return 0

    confirm_seats(
        [
            SeatRequest(
                flight_id=hold.flight_id, cabin=hold.cabin, rbd=hold.rbd, seats=hold.seats
            )
            for hold in holds
        ]
    )
    booking.holds.filter(id__in=[hold.id for hold in holds]).update(released_at=timezone.now())
    return len(holds)


def _request_refund(booking: Booking, payment: Payment) -> Refund:
    """Queue the money back when it arrived for seats we no longer hold."""
    refund = Refund.objects.create(
        booking=booking,
        payment=payment,
        amount=payment.amount,
        currency=payment.currency,
        status=RefundStatus.REQUESTED,
        reason=f"Payment captured after the booking reached {booking.status}.",
        refundable_amount=payment.amount,
    )

    emit(
        "booking",
        booking.pnr,
        "payment_requires_refund",
        {
            "pnr": booking.pnr,
            "contact_email": booking.contact_email,
            "booking_status": booking.status,
            "amount": {"amount": str(payment.amount), "currency": payment.currency},
            "charge_id": payment.provider_charge_id,
        },
    )

    logger.error(
        "payment_after_hold_lost",
        extra={
            "pnr": booking.pnr,
            "status": booking.status,
            "amount": str(payment.amount),
            "charge_id": payment.provider_charge_id,
        },
    )
    return refund


def _post_ledger(booking: Booking, payment: Payment) -> None:
    """What the traveller owes, then what they just paid.

    The sale is only opened once; a later exchange posts its own re-price adjustment, so the
    running balance always has something for a payment to settle against.
    """
    if not booking.ledger_entries.exists():
        post(
            booking,
            LedgerEntryType.SALE,
            debit=Decimal(booking.total_amount),
            reference=booking.pnr,
        )

    post(
        booking,
        LedgerEntryType.PAYMENT,
        credit=Decimal(payment.amount),
        reference=payment.provider_charge_id,
    )


@transaction.atomic
def apply_failed_payment(
    intent: PaymentIntent, *, charge_id: str, code: str = "", message: str = ""
) -> Payment:
    """A decline leaves the hold alone — the traveller can try another card until it expires."""
    existing = Payment.objects.filter(provider_charge_id=charge_id).first()
    if existing is not None:
        return existing

    payment = Payment.objects.create(
        booking=intent.booking,
        intent=intent,
        provider=intent.provider,
        provider_charge_id=charge_id,
        amount=intent.amount,
        currency=intent.currency,
        status=PaymentStatus.FAILED,
        failure_code=code,
        failure_message=message,
    )

    logger.info("payment_failed", extra={"pnr": intent.booking.pnr, "code": code})
    return payment
