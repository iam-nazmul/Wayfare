# features/auth

Staff sign-in. The storefront is anonymous — this exists so the ops console has an identity.

## Responsibilities

- Owns: the login page, the session store, and the role helpers the shell uses to decide what to
  show.
- Does not own: the token lifecycle. Access tokens, the single in-flight refresh, and retry
  queueing live in [api/client.ts](../../api/client.ts).

## Key objects

| Object | Role |
|---|---|
| [store.ts](store.ts) `useAuth` | Who is signed in; mirrors identity, not the token |
| [store.ts](store.ts) `isStaff` / `hasRole` | Role checks for rendering decisions only |
| [api.ts](api.ts) `useLogin` | Exchanges credentials, then reads `/me` |
| [LoginPage.tsx](LoginPage.tsx) | Email + password, redirects by role |

## Invariants

- **The token is set before `/me` is called.** The profile request is authenticated; calling it
  first returns 401 and the sign-in appears to fail.
- **Role checks never authorise anything.** They decide what to render. The API enforces access
  on every request, and a tampered store changes nothing but the nav.
- **Signing out clears the query cache.** Otherwise the next user in the same browser sees the
  previous one's cached bookings.

## Entry points

- `/login` — redirects staff to the ops console and everyone else home.

## Gotchas

- Travellers do not sign in to see a booking. Manage-booking uses PNR + surname, so a login wall
  in front of it would be a regression.
- `is_staff` comes from `/me` because a superuser has no role assignments; without it the ops nav
  would be invisible to an admin who can in fact use it.

## Testing

    make test-fe

Required: staff reach the console; a signed-out visitor is redirected to sign in.
