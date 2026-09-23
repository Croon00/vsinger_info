"""Local typed job boundary; no management HTTP API or legacy DB access."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.schemas.worker_jobs import JobRequest
from app.services import music_jobs


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest='command', required=True)
    for command in ('validate', 'enqueue'):
        commands.add_parser(command).add_argument('--request', type=Path, required=True)
    for command in ('status', 'cancel'):
        commands.add_parser(command).add_argument('--id', type=int, required=True)
    commands.add_parser('readiness')
    commands.add_parser('run-once')
    youtube = commands.add_parser('youtube-url')
    youtube.add_argument('--account-id', type=int, required=True)
    youtube.add_argument('--channel-id', required=True)
    youtube.add_argument('--url', required=True)
    youtube.add_argument('--purpose', choices=('archive', 'cover'), default='archive')
    youtube.add_argument('--request-run', default='initial')
    youtube.add_argument('--validate-only', action='store_true')
    return root


async def execute(args):
    if args.command in ('enqueue', 'cancel', 'run-once') or (args.command == 'youtube-url' and not args.validate_only):
        if not settings.runtime_cutover_enabled:
            raise RuntimeError('Runtime cutover is locked; no job writes or collection are allowed')
        if args.command == 'run-once' and not settings.agent_enabled:
            raise RuntimeError('AGENT_ENABLED is false')
    if args.command == 'youtube-url':
        from app.services.youtube_collection import url_request
        request = url_request(account_id=args.account_id, channel_id=args.channel_id, url=args.url,
                              purpose=args.purpose, request_run=args.request_run)
        if args.validate_only:
            return {'valid': True, 'request': request.model_dump(), 'database_checked': False}
        return {'id': await music_jobs.enqueue(request)}
    if args.command in ('validate', 'enqueue'):
        request = JobRequest.model_validate_json(args.request.read_text(encoding='utf-8-sig'))
        request.parsed_payload()
        if args.command == 'validate':
            return {'valid': True, 'idempotency_key': request.key(), 'database_checked': False}
        return {'id': await music_jobs.enqueue(request)}
    if args.command == 'status':
        result = await music_jobs.status(args.id)
        if result is None:
            raise ValueError('Job does not exist')
        return result
    if args.command == 'cancel':
        return {'id': args.id, 'cancelled': await music_jobs.cancel(args.id)}
    if args.command == 'readiness':
        return await music_jobs.readiness()
    return await music_jobs.run_once()


def main():
    args = parser().parse_args()
    try:
        result = asyncio.run(execute(args))
    except Exception as exc:
        # Validation/DB exceptions can embed payloads or connection strings.
        print(json.dumps({'error': type(exc).__name__,
                          'message': 'Check request, cutover flags, and new DB identity; no legacy fallback.'}))
        return 1
    print(json.dumps(result, default=str, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
