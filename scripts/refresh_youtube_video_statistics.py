"""Refresh cover and linked release video counts without collecting video content."""
import asyncio
import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure
from app.integrations.youtube_video_statistics import fetch_statistics
from app.repositories.youtube_video_statistics import targets, persist


async def main(account_ids=None):
    with catalog_runtime_session() as session:
        requested = targets(session)
        if account_ids:
            requested = [r for r in requested if r['account_id'] in account_ids]
    provider = YouTubeClient(settings.youtube_api_key, interval=2)
    updated = 0
    for offset in range(0, len(requested), 50):
        batch = requested[offset:offset+50]
        found = await fetch_statistics(provider, [r['platform_video_id'] for r in batch], datetime.now(UTC))
        by_id = {r['platform_video_id']: r for r in batch}
        accounts = defaultdict(list)
        for row in found:
            target = by_id[row.video_id]
            if row.channel_id == target['channel_id']:
                accounts[target['account_id']].append(row)
        with catalog_runtime_session() as session:
            for account, rows in accounts.items():
                persist(session, account, rows)
                updated += len(rows)
        print(json.dumps(dict(processed=min(offset+50,len(requested)), requested=len(requested), updated=updated)),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id',type=int,action='append')
    args=parser.parse_args()
    try:
        asyncio.run(main(args.account_id))
    except YouTubeFailure as exc:
        print(json.dumps(dict(stopped=exc.reason)),flush=True)
        raise SystemExit(2) from None
    except Exception as exc:
        print(json.dumps(dict(stopped=type(exc).__name__)),flush=True)
        raise SystemExit(1) from None
