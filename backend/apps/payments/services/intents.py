from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.booking.constants import BookingStatus
from apps.booking.models import Booking
from apps.common.exceptions import InvalidTransition, PaymentFailed
from apps.common.money import Money

from ..constants import INTENT_TTL_MINUTES, IntentStatus
from ..models import PaymentIntent
from ..providers import get_provider

#: An intent is only worth creating while there are seats behind it: a new booking's hold, or
#: the proposed seats of an exchange awaiting its delta.
PAYABLE_STATUSES = frozenset({BookingStatus.HELD, BookingStatus.CHANGE_PENDING})


@transaction.atomic
def create_payment_intent(booking: Booking, *, idempotency_key: str = "") -> PaymentIntent:
    """Open a provider intent for a booking's outstanding balance.

    Re-reads the booking under lock: a hold that expired while the traveller filled the card
    form must not get a payable intent, or we take money for seats we no longer have.
    """
    booking = Booking.objects.select_for_update().get(pk=booking.pk)

    if booking.status not in PAYABLE_STATUSES:
        raise InvalidTransition(f"A {booking.status} booking cannot be paid for.")

    if booking.hold_expires_at and booking.hold_expires_at <= timezone.now():
        raise InvalidTransition("This hold has expired. Search again to rebook.")

    balance = Decimal(booking.total_amount) - Decimal(booking.paid_amount)
    if balance <= 0:
        raise PaymentFailed("This booking has nothing left to pay.")

    # One live intent per booking: a second card form on a second tab must not double-charge.
    existing = (
        PaymentIntent.objects.filter(
            booking=booking,
            status__in=[IntentStatus.REQUIRES_PAYMENT, IntentStatus.REQUIRES_ACTION],
            expires_at__gt=timezone.now(),
            amount=balance,
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return existing

    provider = get_provider()
    result = provider.create_intent(
        amount=Money(balance, booking.currency),
        booking_ref=booking.pnr,
        idempotency_key=idempotency_key or f"intent:{booking.pnr}:{balance}",
        metadata={"pnr": booking.pnr, "public_id": str(booking.public_id)},
    )

    return PaymentIntent.objects.create(
        booking=booking,
        provider=provider.name,
        provider_intent_id=result.intent_id,
        amount=balance,
        currency=booking.currency,
        status=result.status,
        client_secret=result.client_secret,
        three_ds_status=result.three_ds_status,
        idempotency_key=idempotency_key,
        expires_at=timezone.now() + timedelta(minutes=INTENT_TTL_MINUTES),
    )
