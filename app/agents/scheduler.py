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
    collection = await collect_x_once()
    delivery = await deliver_pending_once(bot)
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
    """Run the minimal worker at the configured interval."""
    if not settings.agent_run_on_start:
        await asyncio.sleep(settings.agent_interval_seconds)
    while True:
        try:
            logger.info("agent 실행 완료: %s", await run_agent_once())
        except Exception:
            logger.exception("agent 실행에 실패했습니다.")
        await asyncio.sleep(settings.agent_interval_seconds)
