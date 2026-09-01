from django.db import models

from .uuid7 import uuid7


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublicIdModel(models.Model):
    """Adds the UUIDv7 identifier exposed by the API. Integer PKs never leave the process."""

    public_id = models.UUIDField(default=uuid7, unique=True, editable=False)

    class Meta:
        abstract = True


class IdempotencyKey(TimestampedModel):
    scope = models.CharField(max_length=64)
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="uniq_idempotency_scope_key")
        ]
        indexes = [models.Index(fields=["created_at"], name="idx_idempotency_created")]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"
