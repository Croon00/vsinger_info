"""Durable Discord delivery; an uncertain external send is never retried."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Protocol
from uuid import uuid4

from app.db.catalog_session import catalog_runtime_session
from app.repositories.runtime_delivery import (
    PendingDelivery, claim_deliveries, delivery_is_current, finish_delivery,
    mark_delivery_retry, mark_delivery_sent,
)
from app.services.delivery_errors import DeliveryPermanentError, DeliveryRetryableError, DeliverySkippedError

logger = logging.getLogger(__name__)


class DiscordUrlSender(Protocol):
    def is_available(self) -> bool: ...
    async def send_url(self, channel_id: str, url: str, *, guild_id: str,
                       before_send: Callable[[], bool] | None = None) -> str: ...


@dataclass
class DeliveryResult:
    sent: int = 0
    retried: int = 0
    failed: int = 0
    skipped: int = 0
    unknown: int = 0
    offline: bool = False


def _finish(delivery: PendingDelivery, status: str, error: str) -> bool:
    try:
        with catalog_runtime_session() as session:
            return finish_delivery(session, delivery, status=status, error=error)
    except Exception:
        # A lost DB connection leaves sending -> unknown after lease expiry.
        logger.error("Could not persist %s for delivery %s", status, delivery.id)
        return False


def _save_receipt(delivery: PendingDelivery, message_id: str) -> bool:
    # Only retry the receipt transaction, never the external send.
    for _ in range(3):
        try:
            with catalog_runtime_session() as session:
                if mark_delivery_sent(session, delivery.id, message_id,
                                      worker_id=delivery.lease_owner):
                    return True
            return False
        except Exception:
            logger.warning("Receipt write failed for delivery %s", delivery.id)
    return False


def _is_current(delivery: PendingDelivery) -> bool:
    with catalog_runtime_session() as session:
        return delivery_is_current(session, delivery)


async def deliver_pending_once(
    sender: DiscordUrlSender, *, worker_id: str | None = None,
    limit: int = 100, max_attempts: int = 5, send_timeout_seconds: float = 90,
) -> DeliveryResult:
    if not 0 < send_timeout_seconds < 120:
        raise ValueError("Send timeout must be shorter than its 120 second lease")
    result = DeliveryResult()
    for _ in range(limit):
        if not sender.is_available():
            result.offline = True
            break
        claim_owner = f"{worker_id or 'discord'}-{uuid4()}"
        with catalog_runtime_session() as session:
            deliveries, skipped, unknown = claim_deliveries(
                session, worker_id=claim_owner, limit=1,
            )
        result.skipped += skipped
        result.unknown += unknown
        if not deliveries:
            break
        delivery = deliveries[0]
        if not _is_current(delivery):
            _finish(delivery, "skipped", "route or claim changed before send")
            result.skipped += 1
            continue
        try:
            message_id = await asyncio.wait_for(
                sender.send_url(delivery.channel_id, delivery.source_url,
                                guild_id=delivery.guild_id,
                                before_send=lambda: _is_current(delivery)),
                timeout=send_timeout_seconds,
            )
            if not str(message_id).isdigit():
                raise ValueError("Invalid Discord receipt")
        except asyncio.CancelledError:
            _finish(delivery, "unknown", "send cancelled; acceptance unknown")
            raise
        except DeliveryRetryableError as exc:
            try:
                with catalog_runtime_session() as session:
                    updated = mark_delivery_retry(
                        session, delivery.id, error=type(exc).__name__,
                        attempt_count=delivery.attempt_count, max_attempts=max_attempts,
                        worker_id=delivery.lease_owner, retry_after=exc.retry_after,
                    )
                if not updated:
                    result.unknown += 1
                elif delivery.attempt_count >= max_attempts:
                    result.failed += 1
                else:
                    result.retried += 1
            except Exception:
                _finish(delivery, "unknown", "could not persist confirmed rejection")
                result.unknown += 1
        except DeliverySkippedError:
            _finish(delivery, "skipped", "route or claim changed during channel lookup")
            result.skipped += 1
        except DeliveryPermanentError:
            _finish(delivery, "failed", "Discord rejected destination or permissions")
            result.failed += 1
        except Exception as exc:
            _finish(delivery, "unknown", f"send acceptance unknown: {type(exc).__name__}")
            result.unknown += 1
        else:
            if _save_receipt(delivery, str(message_id)):
                result.sent += 1
            else:
                logger.error("Delivery %s accepted message %s but its receipt is unconfirmed",
                             delivery.id, message_id)
                _finish(delivery, "unknown", f"sent message {message_id}; receipt unconfirmed")
                result.unknown += 1
    return result
