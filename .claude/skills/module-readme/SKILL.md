---
name: module-readme
description: Write or refresh a module README.md for a Django app or frontend feature, targeted at developers and agents. Use when adding a module, when a module's README is missing or stale, or when asked to document a module.
---

# Module README

Every Django app under `backend/apps/` and every frontend feature under `frontend/src/features/`
has a `README.md` **written for developers and agents** — not for end users. The root `README.md`
is the only user-facing document.

Write it in the same commit as the module. A README added later is a README that was guessed.

## Template

```markdown
# <module name>

One or two sentences: what this module owns and where its boundary is.

## Responsibilities

- Owns: <aggregates, tables, or UI surfaces>
- Does not own: <the adjacent thing agents will confuse it with, and where that lives>

## Key objects

| Object | Role |
|---|---|
| `Booking` | … |
| `services/create_booking.py::create_booking` | Entry point for … |

## Invariants

Rules that must hold. State the failure mode, not just the rule.
- Inventory is decremented only inside `_lock_and_reserve_inventory`, under `SELECT … FOR UPDATE`
  ordered by `(flight_id, id)`. Locking in another order deadlocks against the hold-release task.

## Entry points

- HTTP: `POST /api/v1/bookings`, `GET /api/v1/bookings/{pnr}`
- Tasks: `booking.release_expired_holds` (beat, 60 s)
- Events consumed / emitted: `booking_held`, `booking_confirmed`

## Gotchas

Things that have surprised someone. Be specific.

## Testing

    make test app=booking

Which tests are mandatory here and why (e.g. the concurrency test for the last seat).
```

## Rules

- **Actionable over descriptive.** "Call X to do Y" beats "this module handles Y".
- **Point at code**, with clickable relative links: [services/create_booking.py](…).
- **State invariants with their failure mode.** An agent needs to know what breaks.
- **No duplication of SPEC.md** — link to the relevant section instead.
- **No changelog, no history, no rationale essays.**
- Keep it under ~120 lines. If it grows past that, the module is doing too much.

## Refresh triggers

Update the README when: a model or service entry point is added or renamed, an invariant changes,
an endpoint is added, or a gotcha is discovered. A stale README is worse than none — it will be
believed.
