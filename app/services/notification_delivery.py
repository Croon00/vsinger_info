"""Durable Discord URL delivery service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.db.catalog_session import catalog_runtime_session
from app.repositories.runtime_delivery import (
    claim_deliveries,
    mark_delivery_retry,
    mark_delivery_sent,
)


class DiscordUrlSender(Protocol):
    def is_available(self) -> bool: ...
    async def send_url(self, channel_id: str, url: str) -> str: ...


@dataclass
class DeliveryResult:
    sent: int = 0
    retried: int = 0
    failed: int = 0
    skipped: int = 0
    unknown: int = 0
    offline: bool = False


async def deliver_pending_once(
    sender: DiscordUrlSender,
    *,
    worker_id: str | None = None,
    limit: int = 100,
    max_attempts: int = 5,
) -> DeliveryResult:
    """Send due URLs. Offline clients leave pending rows untouched."""
    if not sender.is_available():
        return DeliveryResult(offline=True)
    worker_id = worker_id or f"discord-{uuid4()}"
    with catalog_runtime_session() as session:
        deliveries, skipped, unknown = claim_deliveries(
            session, worker_id=worker_id, limit=limit
        )
    result = DeliveryResult(skipped=skipped, unknown=unknown)
    for delivery in deliveries:
        try:
            message_id = await sender.send_url(delivery.channel_id, delivery.source_url)
            if not str(message_id).isdigit():
                raise ValueError("Discord message id must be numeric")
            with catalog_runtime_session() as session:
                mark_delivery_sent(session, delivery.id, str(message_id))
            result.sent += 1
        except Exception as exc:
            with catalog_runtime_session() as session:
                mark_delivery_retry(
                    session, delivery.id, error=str(exc),
                    attempt_count=delivery.attempt_count, max_attempts=max_attempts,
                )
            if delivery.attempt_count >= max_attempts:
                result.failed += 1
            else:
                result.retried += 1
    return result
