import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import InventoryUnavailable
from apps.inventory.models import Flight
from apps.inventory.services.availability import SeatRequest, hold
from apps.ops.services.outbox import emit
from apps.pricing.constants import PassengerType

from ..constants import BookingStatus, SourceChannel
from ..models import Booking, BookingSegment, InventoryHold, Offer, Passenger
from .pnr import create_with_pnr
from .state import transition

logger = logging.getLogger("wayfare.booking")


@dataclass(frozen=True, slots=True)
class ContactDetails:
    email: str
    phone: str = ""


def _amount(breakdown: dict, key: str) -> Decimal:
    return Decimal(str(breakdown.get(key, {}).get("amount", "0")))


def seats_needed(passengers: list[dict]) -> int:
    """Infants ride on a lap, so they never consume inventory."""
    return sum(1 for p in passengers if p["type"] != PassengerType.INFANT)


@transaction.atomic
def create_booking(
    offer: Offer,
    passengers: list[dict],
    contact: ContactDetails,
    *,
    user=None,
    agency=None,
    source_channel: str = SourceChannel.WEB,
) -> Booking:
    """Turn a validated offer into a held PNR.

    The offer's signature and expiry are already checked by ``load_offer``; what cannot be
    checked ahead of time is whether the seats are still there, so availability is re-read
    under ``SELECT … FOR UPDATE`` inside this transaction. An unexpired offer is not a
    reservation.
    """
    segments = offer.itinerary.get("segments", [])
    if not segments:
        raise InventoryUnavailable("That offer has no flights on it.")

    party = seats_needed(passengers)
    if party == 0:
        raise InventoryUnavailable("A booking needs at least one seated passenger.")

    flights = {
        flight.id: flight
        for flight in Flight.objects.filter(id__in=[s["flight_id"] for s in segments])
    }
    if len(flights) != len({s["flight_id"] for s in segments}):
        raise InventoryUnavailable("A flight on this offer is no longer available.")

    requests = [
        SeatRequest(
            flight_id=segment["flight_id"],
            cabin=segment["cabin"],
            rbd=segment["rbd"],
            seats=party,
        )
        for segment in segments
    ]
    # Raises InventoryUnavailable (409) if the seats went between search and here.
    hold(requests)

    breakdown = offer.price_breakdown
    expires_at = timezone.now() + timedelta(minutes=settings.HOLD_TTL_MINUTES)

    booking = create_with_pnr(
        user=user if user is not None and user.is_authenticated else None,
        agency=agency,
        status=BookingStatus.DRAFT,
        trip_type=offer.search_query.trip_type,
        currency=offer.currency,
        base_amount=_amount(breakdown, "base"),
        tax_amount=_amount(breakdown, "taxes"),
        fee_amount=_amount(breakdown, "fees"),
        discount_amount=_amount(breakdown, "discount"),
        total_amount=offer.total_amount,
        price_breakdown=breakdown,
        contact_email=contact.email,
        contact_phone=contact.phone,
        hold_expires_at=expires_at,
        booked_at=timezone.now(),
        source_channel=source_channel,
    )

    BookingSegment.objects.bulk_create(
        [
            BookingSegment(
                booking=booking,
                flight_id=segment["flight_id"],
                sequence=index,
                cabin=segment["cabin"],
                rbd=segment["rbd"],
                fare_basis=_fare_basis(breakdown, segment["flight_id"]),
                fare_family=offer.fare_family,
                marketing_flight_number=segment["designator"],
            )
            for index, segment in enumerate(segments)
        ]
    )

    _create_passengers(booking, passengers)

    InventoryHold.objects.bulk_create(
        [
            InventoryHold(
                booking=booking,
                offer_id=offer.offer_id,
                flight_id=request.flight_id,
                cabin=request.cabin,
                rbd=request.rbd,
                seats=request.seats,
                expires_at=expires_at,
                hold_key=f"{booking.pnr}:{request.flight_id}",
            )
            for request in requests
        ]
    )

    transition(booking, BookingStatus.HELD, actor=user, reason="offer accepted")

    emit(
        "booking",
        booking.pnr,
        "booking_held",
        {
            "pnr": booking.pnr,
            "public_id": str(booking.public_id),
            "contact_email": booking.contact_email,
            "total": {"amount": str(booking.total_amount), "currency": booking.currency},
            "hold_expires_at": expires_at.isoformat(),
            "segments": [s["designator"] for s in segments],
        },
    )

    logger.info(
        "booking_held",
        extra={"pnr": booking.pnr, "seats": party, "segments": len(segments)},
    )
    return booking


def _fare_basis(breakdown: dict, flight_id: int) -> str:
    for segment in breakdown.get("segments", []):
        if segment.get("flight_id") == flight_id:
            return segment.get("fare_basis", "")
    return ""


def _create_passengers(booking: Booking, passengers: list[dict]) -> None:
    """Seated passengers first, so each infant can point at the adult it travels with.

    The serializer has already guaranteed infants ≤ adults, so pairing by position is enough.
    """
    def build(entry: dict, adult: Passenger | None = None) -> Passenger:
        return Passenger.objects.create(
            booking=booking,
            type=entry["type"],
            first_name=entry["first_name"],
            last_name=entry["last_name"],
            dob=entry["dob"],
            gender=entry.get("gender", ""),
            nationality=entry.get("nationality", ""),
            doc_type=entry.get("doc_type", ""),
            doc_number=entry.get("doc_number", ""),
            doc_expiry=entry.get("doc_expiry"),
            frequent_flyer_number=entry.get("frequent_flyer_number", ""),
            associated_adult=adult,
        )

    adults = [
        build(entry) for entry in passengers if entry["type"] == PassengerType.ADULT
    ]
    for entry in passengers:
        if entry["type"] == PassengerType.CHILD:
            build(entry)

    infants = [entry for entry in passengers if entry["type"] == PassengerType.INFANT]
    for index, entry in enumerate(infants):
        build(entry, adult=adults[index])
