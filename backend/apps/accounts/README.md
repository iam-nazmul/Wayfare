# accounts

Identity, roles, agencies, and saved passenger profiles.

## Responsibilities

- Owns: `User` (email login), role assignments, `Agency` and its credit balance, `Traveller`
  profiles.
- Does not own: passengers on a booking. A `Traveller` is a saved profile the traveller reuses; a
  `Passenger` is an immutable record on a PNR and lives in `apps.booking`. Copying one into the
  other is a booking-time concern.

## Key objects

| Object | Role |
|---|---|
| [models.py](models.py) `User` | `AUTH_USER_MODEL`. Email is the username; there is no username field |
| [models.py](models.py) `UserRole` | Role grant, optionally scoped to an agency |
| [models.py](models.py) `Agency` | B2B account with `credit_limit` / `balance` |
| [models.py](models.py) `Traveller` | Saved passenger, including travel document fields |
| [constants.py](constants.py) `RoleCode` | The seven roles in the SPEC.md §7.3 permission matrix |
| [constants.py](constants.py) `MFA_REQUIRED_ROLES` | Staff roles that must carry a second factor |
| [selectors.py](selectors.py) `travellers_for` | The only read path for travellers |

## Invariants

- **`AUTH_USER_MODEL` was set before the first migration and cannot move.** Swapping the user model
  after `accounts.0001_initial` has been applied anywhere means rebuilding the database.
- **`Traveller.doc_number` is PII.** It is `write_only` in the serializer, on the log redaction
  list, and slated for Fernet encryption at rest in M8. Never add it to a list serializer or a log
  line.
- **Agency credit is not money movement.** `Agency.balance` is a running exposure figure; the
  authoritative record of every charge is the payments ledger. Do not treat `balance` as a
  reconciled account.
- **Role checks read `user.role_codes`,** which hits `role_assignments`. Prefetch it in any list
  endpoint that serializes roles or you get an N+1.

## Entry points

- `POST /api/v1/auth/register` · `login` · `refresh` · `logout`
- `GET|PATCH /api/v1/me`
- `GET|POST|PATCH|DELETE /api/v1/me/travellers[/{public_id}]`

Login and registration carry the `login` throttle scope (10 per 15 minutes per IP).

## Gotchas

- Refresh-token rotation and blacklisting need `rest_framework_simplejwt.token_blacklist` in
  `INSTALLED_APPS` — it is there, and removing it silently turns logout into a no-op.
- `LogoutView` swallows an invalid or expired refresh token on purpose: from the client's point of
  view the session is over either way, and reporting the failure only helps an attacker probe token
  validity.
- `UserRole` is unique on `(user, role, agency)`, so the same role can be granted once per agency
  and once globally (`agency = NULL`). That is deliberate for agents who work across agencies.

## Testing

    make test-be app=accounts

Required: registration rejects duplicate email and weak passwords; a traveller cannot read another
user's travellers (`selectors` filtering); role serialization does not N+1.
