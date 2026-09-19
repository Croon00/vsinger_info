"""Import all cover uploads from every registered official YouTube channel."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.db import init_db
from app.integrations.youtube_channel_monitor import backfill_youtube_covers


async def main() -> None:
    init_db()
    print(await backfill_youtube_covers())


if __name__ == "__main__":
    asyncio.run(main())
