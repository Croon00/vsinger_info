"""Daily public live-page discovery for the site calendar."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.db.catalog_session import catalog_url
from app.integrations.live_site_pages import (
    USER_AGENT, RIOT_INFO_PAGES, ZAIKO_CHANNEL, ZAN_CHANNELS, PublicSiteReader,
    event_links, parse_live_detail,
)
from app.repositories.public_lives import artist_ids_for_event, catalog_artist_rows, save_public_live

logger = logging.getLogger(__name__)
POLL_SECONDS = 24 * 60 * 60


async def poll_live_sites() -> dict[str, int]:
    if not catalog_url():
        logger.info("Live site monitor skipped: DATABASE_URL is unset")
        return {"sources": 0, "details": 0, "created": 0, "failed": 0}
    artists = await asyncio.to_thread(catalog_artist_rows)
    counters = {"sources": 0, "details": 0, "created": 0, "failed": 0}
    sources = {**ZAN_CHANNELS, "riotmusic": ZAIKO_CHANNEL, **RIOT_INFO_PAGES}
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,ja;q=0.9,en;q=0.8"},
        follow_redirects=True,
    ) as client:
        reader = PublicSiteReader(client)
        discovered: dict[str, set[str]] = {}
        for channel, page_url in sources.items():
            try:
                page = await reader.get(page_url)
                counters["sources"] += 1
                links = event_links(page_url, page)
            except (httpx.HTTPError, PermissionError, ValueError):
                logger.exception("Live channel read failed: %s", channel)
                counters["failed"] += 1
                continue
            for url in links:
                discovered.setdefault(url, set()).add(channel)
        for url, channels in discovered.items():
            try:
                detail = parse_live_detail(url, await reader.get(url))
                counters["details"] += 1
                if detail is None or detail.event_date < datetime.now(timezone(timedelta(hours=9))).date():
                    continue
                artist_ids = list(dict.fromkeys(
                    artist_id for channel in channels
                    for artist_id in artist_ids_for_event(artists, channel, detail)
                ))
                if not artist_ids:
                    logger.info("Live event has no catalog artist match: %s", url)
                    continue
                created = await asyncio.to_thread(save_public_live, detail, artist_ids)
                counters["created"] += int(created)
            except (httpx.HTTPError, PermissionError, ValueError, OSError, SQLAlchemyError):
                logger.exception("Live detail failed: %s", url)
                counters["failed"] += 1
    return counters


async def live_site_loop() -> None:
    """Run on startup, then once a day while the Railway service is alive."""
    while True:
        try:
            logger.info("Live site polling finished: %s", await poll_live_sites())
        except Exception:
            logger.exception("Live site polling failed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(poll_live_sites()))
