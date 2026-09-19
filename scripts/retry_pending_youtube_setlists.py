"""Re-read full YouTube comment threads for pending setlists.

The import does not fabricate song data. It saves a setlist only when one
comment contains at least two timestamped song rows, and it keeps title/artist
credits after removing timestamps, ranges, scores, and other display noise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.db import get_connection
from app.integrations.youtube_context import fetch_setlist_comment
from app.integrations.youtube_live_archive import (
    _save_check_result,
    _translate_korean_original_artists,
    parse_setlist_comment,
)


def pending_archives(
    artist_name: str | None,
    limit: int | None,
    include_unassigned: bool,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, youtube_video_id, performer_name
            FROM youtube_live_archives
            WHERE status = 'pending'
              AND (%s OR performer_name IS NOT NULL)
              AND (%s::text IS NULL OR performer_name ILIKE '%%' || %s || '%%')
            ORDER BY COALESCE(broadcast_at, published_at) DESC NULLS LAST, id
            LIMIT %s
            """,
            (include_unassigned, artist_name, artist_name, limit),
        ).fetchall()


async def retry_pending_setlists(
    *,
    artist_name: str | None,
    limit: int | None,
    concurrency: int,
    include_unassigned: bool = False,
) -> dict[str, Any]:
    rows = pending_archives(artist_name, limit, include_unassigned)
    result: dict[str, Any] = {
        "selected": len(rows),
        "setlists_found": 0,
        "still_pending": 0,
        "failed": 0,
        "found_by_artist": {},
    }
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 5)))

    async def retry(row: dict[str, Any]) -> None:
        async with semaphore:
            try:
                context = await fetch_setlist_comment(row["youtube_video_id"])
                setlist = parse_setlist_comment(context.text if context else "")
                await _save_check_result(
                    archive_id=row["id"],
                    comment=context.text if context else None,
                    setlist=setlist,
                    metadata=None,
                )
                if setlist:
                    await _translate_korean_original_artists(row["id"])
                    result["setlists_found"] += 1
                    artist = row["performer_name"] or "(unassigned)"
                    result["found_by_artist"][artist] = result["found_by_artist"].get(artist, 0) + 1
                else:
                    result["still_pending"] += 1
            except Exception:
                result["failed"] += 1

    await asyncio.gather(*(retry(row) for row in rows))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artist", help="Only retry one artist name.")
    parser.add_argument("--limit", type=int, help="Maximum pending archives to retry.")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--include-unassigned", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        retry_pending_setlists(
            artist_name=args.artist,
            limit=args.limit,
            concurrency=args.concurrency,
            include_unassigned=args.include_unassigned,
        )
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
