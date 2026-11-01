"""Slow metadata-only Shorts classification. Never downloads media or changes covers."""
import asyncio
import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.catalog_session import catalog_runtime_session
from app.integrations.youtube_video_format import robots, is_short
from app.repositories.youtube_video_format import targets, persist


async def main(account_ids=None, max_checks=None):
    with catalog_runtime_session() as session:
        rows = targets(session)
        if account_ids:
            rows = [r for r in rows if r['account_id'] in account_ids]
    marked = defaultdict(dict)
    remaining = []
    for row in rows:
        if row['marked']:
            marked[row['account_id']][row['platform_video_id']] = dict(is_short=True,method='title_marker',captured_at=datetime.now(UTC).isoformat())
        else:
            remaining.append(row)
    with catalog_runtime_session() as session:
        for account, values in marked.items():
            persist(session,account,values)
    if max_checks is not None:
        remaining=remaining[:max_checks]
    print(json.dumps(dict(marked_shorts=sum(len(v) for v in marked.values()),url_checks=len(remaining))),flush=True)
    if not remaining:
        return
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        policy = await robots(client)
        for start in range(0,len(remaining),20):
            batch = defaultdict(dict)
            for row in remaining[start:start+20]:
                result = await is_short(client,row['platform_video_id'],policy)
                batch[row['account_id']][row['platform_video_id']] = dict(is_short=result,method='shorts_url_head',captured_at=datetime.now(UTC).isoformat())
                await asyncio.sleep(1)
            with catalog_runtime_session() as session:
                for account, values in batch.items():
                    persist(session,account,values)
            print(json.dumps(dict(checked=min(start+20,len(remaining)),total=len(remaining))),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id',type=int,action='append')
    args=parser.parse_args()
    try:
        asyncio.run(main(args.account_id))
    except Exception as exc:
        print(json.dumps(dict(stopped=type(exc).__name__)),flush=True)
        raise SystemExit(1) from None
