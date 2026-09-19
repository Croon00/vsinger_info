"""Fill Korean song and original-artist labels for recently collected setlists."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.db import get_connection
from app.integrations.youtube_archive_labels import refresh_archive_labels


def archive_ids_since(since: datetime) -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id FROM youtube_live_archives
            WHERE status = 'ready'
              AND performer_name IS NOT NULL
              AND last_checked_at >= %s
            ORDER BY id
            """,
            (since,),
        ).fetchall()
    return [int(row["id"]) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        default="2026-09-18T05:21:41+00:00",
        help="Only translate archives collected on or after this ISO timestamp.",
    )
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    archive_ids = archive_ids_since(since)
    result = asyncio.run(refresh_archive_labels(archive_ids=archive_ids))
    print(json.dumps({"archives": len(archive_ids), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
