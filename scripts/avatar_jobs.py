"""Preview/enqueue initial avatars or inspect/run their independent worker. No music jobs."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.catalog_session import catalog_engine, catalog_url, verify_catalog_identity
from app.repositories import avatar_jobs as repository
from app.services.avatar_jobs import run_once, avatar_worker_loop


def execute(args):
    if args.action in ('run-once', 'worker'):
        return asyncio.run(run_once() if args.action == 'run-once' else avatar_worker_loop())
    with Session(catalog_engine(catalog_url())) as session:
        if not args.apply:
            session.execute(text('SET TRANSACTION READ ONLY'))
        verify_catalog_identity(session)
        if not repository.available(session):
            raise ValueError('Apply catalog migration 007 first')
        if args.action == 'status':
            return repository.get_job(session, args.job_id)
        rows = repository.preview(session, args.artist_id)
        if {r['id'] for r in rows} != set(args.artist_id):
            raise ValueError('Unknown artist ID')
        plans = [{'artist_id': r['id'], 'name': r['name_native'], 'sources': r['sources'],
                  'action': 'skipped_existing' if r['avatar_url'] else 'archived' if r['archived_at'] else
                            'enqueue' if r['sources'] else 'no_source'} for r in rows]
        if args.apply:
            for plan in plans:
                if plan['action'] == 'enqueue':
                    plan['job_id'] = repository.enqueue(session, plan['artist_id'], args.request_run)
            session.commit()
        return {'status': 'committed' if args.apply else 'dry_run', 'plans': plans}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action', required=True)
    enqueue = subs.add_parser('enqueue')
    enqueue.add_argument('--artist-id', type=int, action='append', required=True)
    enqueue.add_argument('--request-run', default='automatic')
    enqueue.add_argument('--apply', action='store_true')
    status = subs.add_parser('status')
    status.add_argument('job_id', type=int)
    subs.add_parser('run-once')
    subs.add_parser('worker')
    args = parser.parse_args()
    if not hasattr(args, 'apply'):
        args.apply = False
    if hasattr(args, 'request_run') and not 1 <= len(args.request_run) <= 120:
        parser.error('request-run must contain 1–120 characters')
    try:
        print(json.dumps(execute(args), ensure_ascii=False, default=str, indent=2))
    except Exception as exc:
        print('Avatar command failed: ' + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
