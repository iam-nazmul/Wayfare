# features/account

The signed-in traveller's own view of what they have booked.

## Responsibilities

- Owns: the "your bookings" list.
- Does not own: the booking detail and servicing screens (`features/manage`), the ticket itself
  (`features/manage/TicketPage`), or sign-in (`features/auth`).
- Not built: profile editing and saved travellers, though `/me` and `/me/travellers` exist.

## Key objects

| Object | Role |
|---|---|
| [api.ts](api.ts) `useMyBookings` | `GET /me/bookings`, ownership-filtered server-side |
| [MyBookingsPage.tsx](MyBookingsPage.tsx) | One row per booking, with Manage and Ticket links |

## Invariants

- **Ownership is the server's answer, not a client filter.** `/me/bookings` runs through
  `bookings_for(actor)`; the page renders whatever comes back and never filters by user itself.
- **Only a ticketed booking offers a ticket.** A held or cancelled one has no e-ticket to show,
  so the link is not rendered.
- **Opening a booking remembers the account's surname.** Manage and ticket pages call the guest
  endpoints, which want `last_name`; for a booking made under the account, the account's own
  surname is the right one.

## Entry points

- `/account/bookings` — signed in only; a signed-out visitor is sent to `/login`.

## Gotchas

- **A booking made while signed out belongs to nobody.** `create_booking` only attaches a user
  when the request was authenticated, so a guest booking never appears in this list — it is
  reachable by PNR + surname through `/manage`. That is deliberate, not a sync bug.
- The list is cursor-paginated (`results` / `next` / `previous`). Only the first page is
  rendered today; a traveller with more than 20 bookings will need the cursor wired up.

## Testing

    make test-fe

Required: the list renders the traveller's own bookings; the ticket link appears only once
ticketed; an empty account points at search and guest retrieval; a signed-out visitor is
redirected.
