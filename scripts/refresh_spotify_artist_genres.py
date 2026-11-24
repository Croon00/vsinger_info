"""Fetch Spotify artist genres for registered catalog owners, preserving all unrelated state."""
import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session
from app.integrations.spotify_artist_genres import fetch_genres
from app.integrations.spotify_catalog import SpotifyCatalogClient, SpotifyFailure
from app.repositories.spotify_artist_genres import targets, persist


async def main(include_disabled=False, account_ids=None):
    with catalog_runtime_session() as session:
        accounts = targets(session, include_disabled=include_disabled)
        if account_ids:
            accounts = [a for a in accounts if a['id'] in account_ids]
    client = SpotifyCatalogClient(settings.spotify_client_id or '', settings.spotify_client_secret or '')
    rows = await fetch_genres(client, [a['platform_id'] for a in accounts], datetime.now(UTC))
    found = {r.spotify_artist_id: r for r in rows}
    with catalog_runtime_session() as session:
        for account in accounts:
            if account['platform_id'] in found:
                persist(session, account['id'], found[account['platform_id']], include_disabled=include_disabled)
    print(json.dumps(dict(requested=len(accounts), updated=len(rows),
                          with_genres=sum(1 for r in rows if r.genres), unavailable=len(accounts) - len(rows))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-registered', action='store_true',
                        help='Include registered accounts whose album collection is disabled, without enabling it')
    parser.add_argument('--account-id', type=int, action='append', help='Refresh only these registered account IDs')
    args = parser.parse_args()
    try:
        asyncio.run(main(include_disabled=args.all_registered, account_ids=args.account_id))
    except SpotifyFailure as exc:
        print(json.dumps(dict(stopped=str(exc))))
        raise SystemExit(2) from None
    except Exception as exc:
        print(json.dumps(dict(stopped=type(exc).__name__)))
        raise SystemExit(1) from None
