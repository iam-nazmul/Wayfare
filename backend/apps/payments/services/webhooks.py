import logging

from django.db import IntegrityError, transaction

from ..models import ProviderWebhookEvent
from ..providers import get_provider

logger = logging.getLogger("wayfare.payments")


def record_event(provider_name: str, body: bytes, signature: str) -> ProviderWebhookEvent | None:
    """Verify and store one callback. Returns ``None`` when it is a replay.

    The unique constraint on ``provider_event_id`` is the deduplication — not a prior SELECT,
    which would still race two concurrent deliveries of the same event.
    """
    provider = get_provider(provider_name)
    event = provider.verify_webhook(body, signature)

    try:
        with transaction.atomic():
            return ProviderWebhookEvent.objects.create(
                provider=provider.name,
                provider_event_id=event.event_id,
                event_type=event.event_type,
                payload=event.payload,
                signature_verified=True,
            )
    except IntegrityError:
        logger.info("webhook_replayed", extra={"event_id": event.event_id})
        return None
