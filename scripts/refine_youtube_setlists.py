"""저장된 YouTube 셋리스트를 영상당 한 번의 OpenAI 호출로 정제합니다."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.integrations.youtube_live_archive import refine_stored_youtube_setlists
from app.core.db import init_db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="정제할 저장 영상 수 제한")
    parser.add_argument("--concurrency", type=int, default=1, help="동시 OpenAI 요청 수 (최대 3)")
    args = parser.parse_args()
    init_db()
    result = asyncio.run(
        refine_stored_youtube_setlists(limit=args.limit, concurrency=args.concurrency)
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
