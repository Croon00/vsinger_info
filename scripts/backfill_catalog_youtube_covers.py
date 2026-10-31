"""Import registered official-channel covers without legacy writes or notifications."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.integrations.youtube_catalog import YouTubeFailure
from app.services.youtube_cover_backfill import backfill


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, default=Path('.tmp/youtube-cover-backfill.json'))
    parser.add_argument('--budget', type=int, default=1500, help='Import requests per rolling 24 hours')
    parser.add_argument('--interval', type=float, default=2, help='Minimum seconds between requests')
    parser.add_argument('--max-pages', type=int, default=2000, help='Per-channel pages per invocation')
    parser.add_argument('--until-complete', action='store_true', help='Wait for the import budget to renew and resume automatically')
    args = parser.parse_args()
    failures = 0
    while True:
        try:
            result = asyncio.run(backfill(settings.youtube_api_key, args.checkpoint,
                budget=args.budget, interval=args.interval, max_pages=args.max_pages))
        except YouTubeFailure as exc:
            print(json.dumps(dict(stopped=exc.reason, retry_after=exc.retry_after)), flush=True)
            failures += 1
            if not args.until_complete or not exc.retry or failures > 5:
                raise SystemExit(2) from None
            time.sleep(max(exc.retry_after, min(60 * 2 ** failures, 1800)))
            continue
        except Exception as exc:
            # Database/transport exceptions can contain credentials; report class only.
            print(json.dumps(dict(stopped=type(exc).__name__)), flush=True)
            raise SystemExit(1) from None
        print(json.dumps(result), flush=True)
        failures = 0
        if not args.until_complete or not result['paused']:
            break
        state = json.loads(args.checkpoint.read_text(encoding='utf-8'))
        recent = [t for t in state['requests'] if t > time.time() - 86400]
        delay = max(1, min(recent) + 86400 - time.time() + 1) if len(recent) >= args.budget else 1
        print(json.dumps(dict(resuming_in_seconds=round(delay))), flush=True)
        time.sleep(delay)


if __name__ == '__main__':
    main()
