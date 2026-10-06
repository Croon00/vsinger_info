"""Queue all researched candidates and run only this request's YouTube jobs.

Default is read-only; enqueue --apply writes typed jobs in batches of at most 200.
The standard collector verifies actual live dates and ownership before saving.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session, catalog_engine, catalog_url, verify_catalog_identity
from app.schemas.worker_jobs import JobRequest
from app.repositories import worker_jobs
from app.services import music_jobs

REPORT = ROOT / 'db-migration/reports/requested-vsingers-2026-10-02'
RUN = 'requested-utawaku-2026-10-03'


def targets():
    items = json.loads((ROOT / 'data/seeds/requested_vsingers_2026_10_02.json').read_text(encoding='utf-8'))['artists']
    for item in items:
        if item['slug'] == 'miran':
            continue
        research = json.loads((REPORT / (item['slug'] + '.json')).read_text(encoding='utf-8'))
        if not research['listing_complete'] or research['channel_id'] != item['channel_id']:
            raise ValueError('Incomplete or conflicting research')
        yield item, list(dict.fromkeys(v['video_id'] for v in research['uploads'] if v['singing_candidate']))


def account_for(session, item):
    rows = session.execute(text("""SELECT e.id,e.collection_enabled FROM external_accounts e
        JOIN artist_external_accounts ae ON ae.account_id=e.id AND ae.relationship='owner'
        JOIN artists a ON a.id=ae.artist_id WHERE a.slug=:slug AND a.archived_at IS NULL
        AND e.platform='youtube' AND e.platform_id=:channel AND e.archived_at IS NULL"""),
        {'slug': item['slug'], 'channel': item['channel_id']}).mappings().all()
    if len(rows) != 1:
        raise ValueError('Missing or conflicting owner')
    count = session.execute(text("SELECT count(*) FROM artist_external_accounts WHERE account_id=:id AND relationship='owner'"), {'id': rows[0]['id']}).scalar_one()
    if count != 1:
        raise ValueError('Shared account needs review')
    return dict(rows[0])


def plan():
    with Session(catalog_engine(catalog_url())) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        verify_catalog_identity(session)
        plans = [{'slug': item['slug'], 'candidates': len(ids), **account_for(session, item)} for item, ids in targets()]
        session.rollback()
    return {'candidates': sum(p['candidates'] for p in plans), 'channels': len(plans), 'plans': plans}


def enqueue(delay_hours):
    if not settings.runtime_cutover_enabled:
        raise ValueError('Runtime cutover is locked')
    total = 0
    for item, ids in targets():
        for offset in range(0, len(ids), 200):
            with catalog_runtime_session() as session:
                session.execute(text('SELECT pg_advisory_xact_lock(731064923)'))
                identity = verify_catalog_identity(session)
                account = account_for(session, item)
                if not account['collection_enabled']:
                    before = session.execute(text('SELECT to_jsonb(e) FROM external_accounts e WHERE id=:id FOR UPDATE'), {'id': account['id']}).scalar_one()
                    after = session.execute(text('UPDATE external_accounts SET collection_enabled=true,version=version+1,updated_at=clock_timestamp() WHERE id=:id RETURNING to_jsonb(external_accounts)'), {'id': account['id']}).scalar_one()
                    digest = hashlib.sha256((RUN + str(account['id'])).encode()).hexdigest()
                    receipt = session.execute(text("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
                        VALUES (:operation,:identity,:hash,'manual',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id"""),
                        {'operation': str(uuid.uuid5(uuid.NAMESPACE_URL, identity + digest)), 'identity': identity, 'hash': digest,
                         'mapping': json.dumps([{'account_id': account['id']}]), 'summary': json.dumps({'policy': RUN, 'collection_enabled': True})}).scalar_one()
                    session.execute(text("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
                        VALUES (:receipt,'external_accounts',:id,'update',CAST(:before AS jsonb),CAST(:after AS jsonb),CAST(:source AS jsonb))"""),
                        {'receipt': receipt, 'id': account['id'], 'before': json.dumps(before), 'after': json.dumps(after),
                         'source': json.dumps({'policy': RUN, 'channel_url': item['channel_url']})})
                jobs = []
                for video in ids[offset:offset+200]:
                    request = JobRequest(job_type='youtube_collect', external_account_id=account['id'],
                        payload={'channel_id': item['channel_id'], 'youtube_video_id': video, 'purpose': 'archive', 'request_run': RUN})
                    payload = request.parsed_payload()
                    jobs.append({'key': request.key(), 'payload': payload.model_dump()})
                worker_jobs.validate_account(session, request, payload)
                inserted = session.execute(text("""INSERT INTO worker_jobs(job_type,idempotency_key,external_account_id,payload,max_attempts,next_attempt_at)
                    SELECT 'youtube_collect',x.key,:account,x.payload,5,clock_timestamp()+(:delay * interval '1 hour')
                    FROM jsonb_to_recordset(CAST(:jobs AS jsonb)) x(key text,payload jsonb)
                    ON CONFLICT(job_type,idempotency_key) DO NOTHING RETURNING id"""),
                    {'account': account['id'], 'jobs': json.dumps(jobs), 'delay': delay_hours}).scalars().all()
                total += len(inserted)
            print(json.dumps({'slug': item['slug'], 'offset': offset, 'new_jobs': len(inserted)}), flush=True)
    print(json.dumps({'new_jobs_total': total, 'request_run': RUN, 'delay_hours': delay_hours}), flush=True)


def status():
    with Session(catalog_engine(catalog_url())) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        verify_catalog_identity(session)
        rows = session.execute(text("""SELECT status,count(*) count,min(next_attempt_at) next_attempt_at
            FROM worker_jobs WHERE payload->>'request_run'=:run GROUP BY status ORDER BY status"""), {'run': RUN}).mappings().all()
        session.rollback()
    return {'request_run': RUN, 'jobs': [dict(r) for r in rows]}


async def worker():
    if not (settings.runtime_cutover_enabled and settings.agent_enabled):
        raise ValueError('Worker execution is locked')
    print(json.dumps({'status': 'worker_started', 'request_run': RUN}), flush=True)
    while True:
        try:
            result = await music_jobs.run_once(kinds=('youtube_collect',), request_run=RUN, worker_name=RUN)
        except Exception as exc:
            print(json.dumps({'status': 'worker_error', 'error_type': type(exc).__name__}), flush=True)
            await asyncio.sleep(30)
            continue
        if result['status'] != 'idle':
            print(json.dumps(result), flush=True)
        else:
            counts = status()['jobs']
            if not any(r['status'] in ('pending', 'retry', 'running') for r in counts):
                print(json.dumps({'status': 'finished', 'summary': status()}, default=str), flush=True)
                return
        await asyncio.sleep(30 if result['status'] == 'idle' else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'enqueue', 'status', 'worker'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--delay-hours', type=float, default=24)
    args = parser.parse_args()
    if args.delay_hours < 0:
        parser.error('delay must not be negative')
    if args.command == 'worker':
        asyncio.run(worker())
    elif args.command == 'enqueue' and args.apply:
        enqueue(args.delay_hours)
    else:
        print(json.dumps(status() if args.command == 'status' else plan(), default=str))


if __name__ == '__main__':
    main()
