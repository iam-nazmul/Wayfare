from django.db import models

from apps.common.models import TimestampedModel


class OutboxEvent(TimestampedModel):
    """A side effect promised inside a transaction and delivered after it commits.

    Nothing that leaves the process — email, webhook, PDF, ClickHouse write — happens inline.
    Writing the row is part of the business transaction, so a rollback cannot leave a customer
    holding a confirmation for a booking that does not exist.
    """

    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    available_at = models.DateTimeField(db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["processed_at", "available_at"],
                name="idx_outbox_pending",
                condition=models.Q(processed_at__isnull=True),
            ),
            models.Index(fields=["aggregate_type", "aggregate_id"], name="idx_outbox_aggregate"),
        ]
        ordering = ["available_at"]

    def __str__(self) -> str:
        return f"{self.event_type} {self.aggregate_type}:{self.aggregate_id}"


class AuditLog(TimestampedModel):
    """Who changed what, and what it looked like either side of the change."""

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_entries",
    )
    actor_type = models.CharField(max_length=20, default="SYSTEM")
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=32)
    object_id = models.CharField(max_length=64)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="idx_audit_object"),
            models.Index(fields=["-created_at"], name="idx_audit_recent"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"
