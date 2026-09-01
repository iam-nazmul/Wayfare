# Wayfare

Search, book, and manage flights — from fare search through payment, e-ticket, check-in, and
refunds.

Wayfare runs the whole commercial life of a seat: schedules and seat inventory, fare products and
taxes, booking with a real PNR, card payment, e-ticket issuance with per-segment coupons, seat
selection, check-in and boarding passes, plus changes, cancellations, and refunds.

## Run it

You need [Docker](https://docs.docker.com/get-started/get-docker/) with Compose v2. Nothing else —
Python, Node, Postgres, Redis, and ClickHouse all run in containers.

```bash
git clone git@github.com:iam-nazmul/Wayfare.git
cd Wayfare
make up      # builds and starts everything, creates .env on first run
make seed    # loads demo airports, flights, fares and users
```

Then open:

| What | Where |
|---|---|
| Storefront | http://localhost |
| API documentation | http://localhost/api/docs/ |
| Admin | http://localhost/admin/ |
| Email inbox (dev) | http://localhost:8025 |
| Background jobs | http://localhost:5555 |

`make down` stops everything and keeps your data. `make clean` also deletes it.

## Demo accounts

`make seed` creates these. They only exist on your machine.

| Account | Email | Password |
|---|---|---|
| Traveller | demo@wayfare.local | `wayfare-demo-1` |
| Agency agent | agency@wayfare.local | `wayfare-demo-1` |
| Airline ops | ops@wayfare.local | `wayfare-demo-1` |

## Test payments

Dev runs a sandbox payment provider — no real money, no real card processor. Use these numbers:

| Card number | Result |
|---|---|
| 4242 4242 4242 4242 | Payment succeeds |
| 4000 0000 0000 0002 | Card declined |
| 4000 0000 0000 3220 | Asks for 3-D Secure |

## What you can do

- **Search** one-way, return, and multi-city trips, with connections and a cheapest-fare calendar.
- **Book** for adults, children, and infants, with travel documents and special service requests.
- **Add extras** — seats, bags, meals, priority boarding.
- **Pay** by card, or on agency credit if you book as an agency.
- **Manage** a booking with your reference and surname: change flights, cancel, request a refund.
- **Check in** from 48 hours before departure and download a boarding pass.
- **Run the airline side** from the ops console: schedules, seat inventory, fares, passenger
  manifests, refund approvals, and reporting.

## Commands

```
make up        start everything            make down      stop, keep data
make seed      load demo data              make clean     stop, delete data
make test      run the test suite          make logs s=api  tail one service
make migrate   apply database migrations   make help      list every command
```

## Documentation

- [SPEC.md](SPEC.md) — full functional and technical specification
- [CLAUDE.md](CLAUDE.md) — architecture and working rules for developers
- Module guides live in each app's own `README.md`

## Project status

Under active development, built milestone by milestone (see [SPEC.md](SPEC.md) §16). Milestone M0
— the foundation, containers, API skeleton, and CI — is complete. Search, booking, payment, and
ticketing land in M2–M4.

## Licence

Proprietary. All rights reserved.
