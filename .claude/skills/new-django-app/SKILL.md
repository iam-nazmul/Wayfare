---
name: new-django-app
description: Scaffold a new Wayfare Django app with the house layout (services/, selectors.py, tests/, module README). Use when adding a new backend domain module under backend/apps/, or when an existing app needs to be reshaped to the standard layout.
---

# New Django app

Read [django-app-layout.md](../../references/django-app-layout.md) first — it is the authority on
structure and layer responsibilities.

## Steps

1. **Confirm it needs its own app.** A new app is justified by its own aggregate root and lifecycle.
   If it is a few models hanging off an existing aggregate, extend that app instead.

2. **Create and reshape.**
   ```bash
   docker compose run --rm api python manage.py startapp <name> apps/<name>
   ```
   Then produce the standard tree: `services/`, `selectors.py`, `constants.py`, `tests/factories.py`.
   Delete `views.py`/`tests.py` stubs you are not filling in this change.

3. **Register.** Add `apps.<name>` to `INSTALLED_APPS` in `config/settings/base.py`. Mount
   `urls.py` under `/api/v1/` in `config/urls.py` only when there are endpoints.

4. **Models.** Inherit `TimestampedModel`, add `PublicIdModel` if API-addressable. Statuses as
   `TextChoices` in `constants.py`. Express every invariant as a DB `CheckConstraint` or
   `UniqueConstraint`, not only in Python. Index what you filter on.

5. **Migration.** Generate, then read it. Reject: data loss, unindexed FKs, `ALTER` that rewrites a
   hot table, `RunPython` without a reverse.
   ```bash
   make migrate
   ```

6. **Services and selectors.** Writes in `services/<verb>.py` (keyword-only args, explicit `actor`,
   one `transaction.atomic()`, domain exceptions, outbox for side effects). Reads in
   `selectors.py`, ownership-filtered, with `select_related`/`prefetch_related`.

7. **Factories and tests** — `tests/factories.py` before the first test. See
   [testing-patterns.md](../../references/testing-patterns.md).

8. **Module README** — same commit. Use the `module-readme` skill.

9. **Verify.**
   ```bash
   make lint && make test
   ```

## Checklist before finishing

- [ ] Layout matches the reference exactly
- [ ] No business logic in `views.py`, `models.save()`, or signals
- [ ] Every read path is ownership-filtered in `selectors.py`
- [ ] Constraints in the DB, not just in Python
- [ ] `README.md` written for developers/agents
- [ ] Factories exist; services have tests
