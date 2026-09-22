"""Minimal Discord connection used only for X post URL delivery."""
from __future__ import annotations

import logging

from app.core.config import settings

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
            super().__init__(intents=discord.Intents.none())

        async def setup_hook(self) -> None:
            # Remote command deletion is an explicit deployment operation in phase 6.
            # This client intentionally does not construct or sync a CommandTree.
            logger.info("Discord URL delivery client initialized without commands")

        def is_available(self) -> bool:
            return not self.is_closed() and self.is_ready()

        async def send_url(self, channel_id: str, url: str) -> str:
            """Send exactly one source URL to an already configured route channel."""
            if not self.is_available():
                raise RuntimeError("Discord client is offline")
            channel = self.get_channel(int(channel_id))
            if channel is None or not hasattr(channel, "send"):
                raise LookupError(f"Discord channel is unavailable: {channel_id}")
            message = await channel.send(url)
            return str(message.id)
else:
    class ScheduleMusicBot:
        """Offline placeholder used when discord.py cannot load."""

        def is_available(self) -> bool:
            return False

        async def send_url(self, channel_id: str, url: str) -> str:
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
