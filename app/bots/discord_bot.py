"""Minimal Discord connection used only for X post URL delivery."""
from __future__ import annotations

import logging
from typing import Callable

from app.core.config import settings
from app.services.delivery_errors import (
    DeliveryPermanentError, DeliveryRetryableError, DeliverySkippedError, DeliveryUncertainError,
)

logger = logging.getLogger(__name__)

try:
    import discord
except ModuleNotFoundError as exc:  # Python runtimes without discord's audio dependency
    if exc.name != "audioop":
        raise
    discord = None
    logger.warning("Discord client dependency is unavailable: %s", exc)


if discord is not None:
    class ScheduleMusicBot(discord.Client):
        """Discord client with no commands, interactions, or management behavior."""

        def __init__(self) -> None:
            intents = discord.Intents.none()
            intents.guilds = True
            super().__init__(intents=intents, max_ratelimit_timeout=30)

        async def setup_hook(self) -> None:
            # Remote command deletion is an explicit deployment operation in phase 6.
            # This client intentionally does not construct or sync a CommandTree.
            logger.info("Discord URL delivery client initialized without commands")

        def is_available(self) -> bool:
            return not self.is_closed() and self.is_ready()

        async def send_url(self, channel_id: str, url: str, *, guild_id: str,
                           before_send: Callable[[], bool] | None = None) -> str:
            """Send exactly one source URL to an already configured route channel."""
            if not self.is_available():
                raise DeliveryRetryableError("Discord client is offline")
            try:
                channel = self.get_channel(int(channel_id))
                if channel is None:
                    channel = await self.fetch_channel(int(channel_id))
                guild = getattr(channel, "guild", None)
                if guild is None or str(guild.id) != guild_id or not hasattr(channel, "send"):
                    raise DeliveryPermanentError("Channel does not belong to the route guild")
                member = guild.me
                if member is None:
                    if self.user is None:
                        raise DeliveryRetryableError("Bot identity is not ready")
                    member = await guild.fetch_member(self.user.id)
                permissions = channel.permissions_for(member)
                can_send = (permissions.send_messages_in_threads
                            if isinstance(channel, discord.Thread) else permissions.send_messages)
                if not permissions.view_channel or not can_send:
                    raise DeliveryPermanentError("Bot lacks channel send permissions")
            except (DeliveryPermanentError, DeliveryRetryableError):
                raise
            except (discord.Forbidden, discord.NotFound) as exc:
                raise DeliveryPermanentError("Discord destination is inaccessible") from exc
            except discord.RateLimited as exc:
                raise DeliveryRetryableError("Channel lookup rate limited", retry_after=exc.retry_after) from exc
            except Exception as exc:
                # No POST has been attempted, so lookup failures are safe to retry.
                raise DeliveryRetryableError("Channel lookup failed") from exc
            # A REST channel/member lookup may have taken time. Recheck the
            # service-owned route/lease immediately before attempting the POST.
            if before_send is not None and not before_send():
                raise DeliverySkippedError("Route or claim changed before POST")
            if not self.is_available():
                raise DeliveryRetryableError("Discord disconnected before POST")
            try:
                message = await channel.send(url)
            except (discord.Forbidden, discord.NotFound) as exc:
                raise DeliveryPermanentError("Discord rejected message destination") from exc
            except discord.RateLimited as exc:
                raise DeliveryRetryableError("Discord rate limited", retry_after=exc.retry_after) from exc
            except discord.HTTPException as exc:
                if exc.status == 429:
                    delay = float(exc.response.headers.get("Retry-After", 30))
                    raise DeliveryRetryableError("Discord rate limited", retry_after=delay) from exc
                if 400 <= exc.status < 500:
                    raise DeliveryPermanentError("Discord rejected message") from exc
                raise DeliveryUncertainError("Discord send result unknown") from exc
            except Exception as exc:
                raise DeliveryUncertainError("Discord send result unknown") from exc
            return str(message.id)
else:
    class ScheduleMusicBot:
        """Offline placeholder used when discord.py cannot load."""

        def is_available(self) -> bool:
            return False

        async def send_url(self, channel_id: str, url: str, *, guild_id: str,
                           before_send: Callable[[], bool] | None = None) -> str:
            raise RuntimeError("Discord client dependency is unavailable")

        async def start(self, token: str) -> None:
            raise RuntimeError("Discord client dependency is unavailable")


bot = ScheduleMusicBot()


async def start_discord_bot() -> None:
    """Start the delivery-only client when a bot token is configured."""
    if not settings.discord_bot_token:
        logger.warning("DISCORD_BOT_TOKEN이 없어 Discord URL 전송을 비활성화합니다.")
        return
    await bot.start(settings.discord_bot_token)
