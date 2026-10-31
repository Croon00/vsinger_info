"""Fetch statistics for registered catalog owners, preserving all unrelated state."""
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure
from app.integrations.youtube_channel_statistics import fetch_statistics
from app.repositories.youtube_channel_statistics import targets, persist


async def main():
    with catalog_runtime_session() as session:
        accounts = targets(session)
    rows = await fetch_statistics(YouTubeClient(settings.youtube_api_key, interval=2),
                                  [a['platform_id'] for a in accounts], datetime.now(UTC))
    found = {r.channel_id: r for r in rows}
    with catalog_runtime_session() as session:
        for account in accounts:
            if account['platform_id'] in found:
                persist(session, account['id'], found[account['platform_id']])
    print(json.dumps(dict(requested=len(accounts), updated=len(rows), unavailable=len(accounts)-len(rows))))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except YouTubeFailure as exc:
        print(json.dumps(dict(stopped=exc.reason)))
        raise SystemExit(2) from None
    except Exception as exc:
        print(json.dumps(dict(stopped=type(exc).__name__)))
        raise SystemExit(1) from None
