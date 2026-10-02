"""Unified-DB X polling and durable Discord URL delivery loop."""
from __future__ import annotations

import asyncio
import logging

from app.bots.discord_bot import bot
from app.core.config import settings
from app.services.notification_delivery import deliver_pending_once
from app.services.x_collection import collect_x_once

logger = logging.getLogger(__name__)


async def run_agent_once() -> dict[str, int | bool]:
    """Run X collection and Discord delivery without other collectors or Google."""
    collection, delivery = await asyncio.gather(
        collect_x_once(poll_interval_seconds=max(1, settings.agent_interval_seconds)),
        deliver_pending_once(bot),
        return_exceptions=True,
    )
    for result in (collection, delivery):
        if isinstance(result, BaseException):
            raise result
    return {
        "accounts": collection.accounts,
        "posts_seen": collection.posts_seen,
        "posts_stored": collection.posts_stored,
        "deliveries_queued": collection.deliveries_queued,
        "collection_failures": collection.failures,
        "notifications_sent": delivery.sent,
        "notifications_retried": delivery.retried,
        "notifications_failed": delivery.failed,
        "notifications_skipped": delivery.skipped,
        "notifications_unknown": delivery.unknown,
        "discord_offline": delivery.offline,
    }


async def agent_loop() -> None:
    """Independent clocks: due X accounts and Discord retries cannot block each other."""
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(_x_loop())
        tasks.create_task(_delivery_loop())


async def _x_loop() -> None:
    interval = max(1, settings.agent_interval_seconds)
    if not settings.agent_run_on_start:
        await asyncio.sleep(interval)
    while True:
        provider_wait_seconds = 0
        try:
            result = await collect_x_once(poll_interval_seconds=interval)
            provider_wait_seconds = result.provider_wait_seconds
            if result.accounts or result.failures:
                logger.info("X collection: %s", result)
        except Exception:
            logger.error("X collection cycle failed")
        # A shared twscrape account limit applies to every target X account.
        # Leave Discord delivery on its independent loop while X waits.
        await asyncio.sleep(max(min(10, interval), provider_wait_seconds))


async def _delivery_loop() -> None:
    while True:
        try:
            result = await deliver_pending_once(bot)
            if any((result.sent, result.retried, result.failed, result.skipped, result.unknown)):
                logger.info("Discord delivery: %s", result)
        except Exception:
            logger.error("Discord delivery cycle failed")
        await asyncio.sleep(5)
