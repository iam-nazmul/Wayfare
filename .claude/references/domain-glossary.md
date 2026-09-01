# Airline domain glossary

Terms an agent needs to read Wayfare code correctly. Model detail: [SPEC.md](../../SPEC.md) §5.

## Order and document

| Term | Meaning in Wayfare |
|---|---|
| **PNR** | The reservation. 6-char locator on `Booking`. Holds passengers, segments, ancillaries. |
| **Offer** | A priced, signed, 15-min search result. Not a reservation — holds nothing. |
| **Hold** | A 20-min inventory lock created when a booking is made from an offer. |
| **E-ticket** | `Ticket` — one per passenger, 13 digits: 3-digit airline prefix + 9-digit serial + check digit (`serial mod 7`). |
| **Coupon** | `TicketCoupon` — one per segment. The unit that is flown, exchanged, or refunded. |
| **EMD** | Receipt for an ancillary (bag, seat, meal). Separate document from the ticket. |
| **Conjunction ticket** | When an itinerary exceeds 4 coupons, tickets link via `conjunction_of`. |
| **Void** | Cancelling a ticket on the day of issue with all coupons `OPEN`. No penalty, no refund flow. |
| **Exchange / reissue** | Change: old coupons → `EXCHANGED`, new ticket issued, fare difference + change fee collected. |

## Inventory and pricing

| Term | Meaning |
|---|---|
| **Cabin** | Physical class: `ECONOMY`, `PREMIUM_ECONOMY`, `BUSINESS`, `FIRST`. `CabinConfig.capacity` is the hard ceiling. |
| **RBD / booking class** | Single-letter bucket inside a cabin (Y, B, M, Q…). `BookingClass.authorised` may sum above cabin capacity — that is intentional nesting, not a bug. Overselling *seats* is a bug. |
| **Authorisation** | Seats a given RBD is allowed to sell. Revenue management raises/lowers it to steer price. |
| **Fare family** | Marketed bundle — Basic / Standard / Flex. Carries changeability, refundability, baggage. |
| **Fare basis** | Code identifying the priced fare, e.g. `QLOWBD`. |
| **Advance purchase (AP)** | Minimum days before departure a fare may be sold. |
| **Min/max stay** | Constraints on the return date for round trips. |
| **Load factor** | Seats sold ÷ capacity. |
| **Oversell allowance** | Seats sellable above capacity. Defaults to 0 in v1. |

## Journey

| Term | Meaning |
|---|---|
| **Slice** | One directional journey requested in a search (outbound, or return). |
| **Segment** | One marketed flight in an itinerary — what a coupon maps to. |
| **Leg** | A physical hop. A segment with a technical stop covers two legs. |
| **MCT** | Minimum connect time. 45 min domestic / 90 min international, overridable per airport. |
| **Stopover vs. connection** | Over 24 h is a stopover (a separate journey); under is a connection. |

## Passenger

| Term | Meaning |
|---|---|
| **ADT / CHD / INF** | Adult (12+), child (2–11), infant (<2). Age is evaluated at the **return** date. |
| **Infant on lap** | No seat, must reference an adult on the same booking (`associated_adult`). |
| **APIS** | Advance Passenger Information — travel document data. Required for international check-in. |
| **SSR** | Special Service Request: `WCHR` wheelchair, `VGML` vegetarian meal, `UMNR` unaccompanied minor. |
| **BCBP** | IATA Bar Coded Boarding Pass — the M-format string encoded in the boarding pass barcode. |

## Money

| Term | Meaning |
|---|---|
| **Base fare** | The fare before taxes. What the airline earns. |
| **Taxes / fees / carrier surcharge** | Added per itinerary and per airport/country. Some are non-refundable even on refundable fares. |
| **Penalty** | Amount retained on cancellation, per fare family and time-to-departure. |
| **Residual value** | Leftover credit after an exchange to a cheaper fare. Only some fare families allow it. |
| **Net fare vs. published fare** | Agency pricing models. Wayfare v1 carries `commission_pct` but has no settlement flow. |

## Status vocabularies

```
Flight    SCHEDULED DELAYED BOARDING DEPARTED ARRIVED CANCELLED DIVERTED
Booking   DRAFT HELD PENDING_TICKETING CONFIRMED TICKETED CHANGE_PENDING
          DISRUPTED REBOOKED CANCELLED EXPIRED REFUND_PENDING REFUNDED
Coupon    OPEN CHECKED_IN FLOWN EXCHANGED REFUNDED VOID
Payment   REQUIRES_PAYMENT PROCESSING SUCCEEDED FAILED REFUNDED PARTIALLY_REFUNDED
Seat      AVAILABLE HELD ASSIGNED BLOCKED
```

## Traps

- An **offer is not a reservation** — availability must be re-checked at booking time.
- A **coupon is refunded individually**; a partially flown ticket refunds only unflown coupons,
  and the fare is recalculated for the flown portion.
- **Infants do not consume seat inventory** but do consume the adult-association slot.
- **Local vs. UTC**: schedules are authored in local time; a DST shift moves the UTC departure of
  every materialised flight. Always store both.
- **Arrival day offset** — a flight arriving after midnight has `arrival_day_offset = 1`.
  Dropping it produces negative durations.
