from ..models import AuditLog


def record(
    action: str,
    object_type: str,
    object_id: str,
    *,
    actor=None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
) -> AuditLog:
    signed_in = actor is not None and getattr(actor, "is_authenticated", False)

    return AuditLog.objects.create(
        actor=actor if signed_in else None,
        actor_type="USER" if signed_in else "SYSTEM",
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before=before or {},
        after=after or {},
        reason=reason,
    )
