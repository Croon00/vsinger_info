"""Register the requested channel and reuse the guarded, request-scoped backfill.

Research first with prepare_requested_vsingers.py using SEED and REPORT below.
Registration and enqueue are dry-run unless --apply is supplied. Worker runs only
this request's YouTube jobs; no Discord, Spotify or Calendar handlers are started.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import sys
import uuid
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import backfill_requested_utawaku as backfill
from scripts import register_requested_vsingers as registration
from scripts.migrate_catalog import configure_transaction, load_connection
from app.core.config import settings
from app.db.catalog_session import catalog_engine, catalog_url, verify_catalog_identity
from app.integrations.youtube_catalog import YouTubeClient, purpose
from app.repositories.youtube_collection import _document
from app.services import music_jobs
from app.repositories import worker_jobs

SEED = ROOT / 'data/seeds/nakamachi_arale_2026_10_07.json'
REPORT = ROOT / 'db-migration/reports/nakamachi-arale-2026-10-07'
RUN = 'nakamachi-arale-utawaku-2026-10-07'
SLUG = 'nakamachi-arale'


def targets():
    for item in json.loads(SEED.read_text(encoding='utf-8'))['artists']:
        research = json.loads((REPORT / (item['slug'] + '.json')).read_text(encoding='utf-8'))
        if research.get('status') != 'resolved' or not research.get('listing_complete') or research['channel_id'] != item['channel_id']:
            raise ValueError('Incomplete or conflicting channel research')
        yield item, list(dict.fromkeys(v['video_id'] for v in research['uploads'] if v['singing_candidate']))


def register_aliases(conn, items):
    changes = []
    for item in items:
        artist = conn.execute('SELECT id FROM artists WHERE slug=%s AND archived_at IS NULL', (item['slug'],)).fetchone()[0]
        for alias in item.get('aliases', []):
            normalized = ' '.join(unicodedata.normalize('NFKC', alias).casefold().split())
            row = conn.execute('''INSERT INTO artist_aliases(artist_id,alias,normalized_alias) VALUES (%s,%s,%s)
                ON CONFLICT(artist_id,normalized_alias) DO NOTHING RETURNING id,to_jsonb(artist_aliases)''',
                (artist, alias, normalized)).fetchone()
            if row:
                changes.append((row[0], row[1], item['channel_url']))
    if changes:
        identity = conn.execute('SELECT id::text FROM catalog_instance').fetchone()[0]
        digest = hashlib.sha256(json.dumps(changes, sort_keys=True).encode()).hexdigest()
        receipt = conn.execute('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'manual',%s,%s) RETURNING id''',
            (uuid.uuid5(uuid.NAMESPACE_URL, identity + RUN + ':aliases:' + digest), identity, digest,
             Jsonb([{'entity_type': 'artist_aliases', 'id': key} for key, _, _ in changes]), Jsonb({'aliases_created': len(changes)}))).fetchone()[0]
        for key, after, url in changes:
            conn.execute('''INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,after_data,provenance)
                VALUES (%s,'artist_aliases',%s,'create',%s,%s)''',
                (receipt, key, Jsonb(after), Jsonb({'source_url': url, 'policy': RUN + '-aliases'})))
    return len(changes)


async def save_broadcasts(write=False):
    """Bounded metadata import; retain setlist jobs and all existing catalog rows."""
    item, ids = next(targets())
    videos = await YouTubeClient(settings.youtube_api_key).videos(ids)
    eligible = [v for v in videos if v.channel_id == item['channel_id'] and v.availability == 'public' and purpose(v) == 'archive']
    captured = datetime.now(UTC)
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'verified-broadcasts.json').write_text(json.dumps({
        'captured_at': captured.isoformat(), 'candidate_count': len(ids),
        'returned_count': len(videos), 'eligible': [v.model_dump(mode='json') for v in eligible],
        'excluded_ids': [v.id for v in videos if v not in eligible],
        'unavailable_ids': sorted(set(ids) - {v.id for v in videos}),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'candidates': len(ids), 'returned': len(videos), 'verified_broadcasts': len(eligible), 'created': 0}
    if not write:
        return summary
    with Session(catalog_engine(catalog_url())) as session, session.begin():
        identity = verify_catalog_identity(session)
        session.execute(text('SELECT pg_advisory_xact_lock(731064923)'))
        account = backfill.account_for(session, item)
        artist = session.execute(text('SELECT id FROM artists WHERE slug=:slug AND archived_at IS NULL'), {'slug': item['slug']}).scalar_one()
        changes = []
        for video in eligible:
            session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:id,941203))'), {'id': video.id})
            existing = session.execute(text("SELECT id,source_account_id,archived_at FROM videos WHERE platform='youtube' AND platform_video_id=:id FOR UPDATE"), {'id': video.id}).mappings().one_or_none()
            if existing and (existing['archived_at'] or existing['source_account_id'] not in (None, account['id'])):
                raise ValueError('Existing video ownership or archive conflict')
            if existing:
                video_id = existing['id']
            else:
                row = session.execute(text("""INSERT INTO videos(platform,platform_video_id,source_account_id,title,published_at,duration_seconds,availability)
                    VALUES ('youtube',:external,:account,:title,:published,:duration,:availability) RETURNING id,to_jsonb(videos) after_data"""),
                    dict(external=video.id, account=account['id'], title=video.title, published=video.published_at, duration=video.duration_seconds, availability=video.availability)).mappings().one()
                video_id = row['id']
                changes.append(('videos', video_id, row['after_data']))
            archive = session.execute(text('SELECT id,archived_at FROM live_archives WHERE video_id=:id FOR UPDATE'), {'id': video_id}).mappings().one_or_none()
            if archive:
                if archive['archived_at']:
                    raise ValueError('Archived broadcast requires review')
                continue
            if session.execute(text('SELECT id FROM covers WHERE video_id=:id'), {'id': video_id}).first():
                raise ValueError('Video already classified as cover')
            row = session.execute(text("""INSERT INTO live_archives(video_id,primary_artist_id,broadcast_at,setlist_state)
                VALUES (:video,:artist,:broadcast,'unprocessed') RETURNING id,to_jsonb(live_archives) after_data"""),
                dict(video=video_id, artist=artist, broadcast=video.started_at)).mappings().one()
            archive_id = row['id']
            changes.append(('live_archives', archive_id, row['after_data']))
            row = session.execute(text("INSERT INTO archive_artists(archive_id,artist_id,role,position) VALUES (:archive,:artist,'host',0) RETURNING id,to_jsonb(archive_artists) after_data"), dict(archive=archive_id, artist=artist)).mappings().one()
            changes.append(('archive_artists', row['id'], row['after_data']))
            document, _ = _document(session, video_id=video.id, kind='video_description', external_id=video.id,
                content=video.description, metadata={'collector': RUN + '-metadata', 'video': video.model_dump(mode='json')},
                disposition='applied', captured_at=captured)
            session.execute(text("INSERT INTO archive_sources(archive_id,document_id,role) VALUES (:archive,:document,'metadata_evidence') ON CONFLICT DO NOTHING"), dict(archive=archive_id, document=document))
            summary['created'] += 1
        if changes:
            digest = hashlib.sha256(json.dumps(changes, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
            receipt = session.execute(text("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
                VALUES (:operation,:identity,:digest,'manual',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id"""),
                dict(operation=str(uuid.uuid5(uuid.NAMESPACE_URL, identity + RUN + digest)), identity=identity, digest=digest,
                     mapping=json.dumps([{'entity_type': t, 'id': key} for t, key, _ in changes]), summary=json.dumps(summary))).scalar_one()
            for table, key, after in changes:
                session.execute(text("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,after_data,provenance)
                    VALUES (:receipt,:table,:key,'create',CAST(:after AS jsonb),CAST(:source AS jsonb))"""),
                    dict(receipt=receipt, table=table, key=key, after=json.dumps(after), source=json.dumps({'policy': RUN + '-metadata', 'channel_url': item['channel_url']})))
    return summary


async def resume_setlists():
    if not (settings.runtime_cutover_enabled and settings.agent_enabled):
        raise ValueError('Worker execution is locked')
    verified_after = datetime.now(UTC)
    item, ids = next(targets())
    provider = YouTubeClient(settings.youtube_api_key)
    # Probe both metadata and the comment endpoint with the newly loaded key.
    videos = await provider.videos(ids[:1])
    if len(videos) != 1 or videos[0].channel_id != item['channel_id']:
        raise ValueError('Credential probe did not resolve the requested channel')
    await provider.comments(videos[0].id)
    recovered = await music_jobs.db_call(recover_request_retries, verified_after)
    print(json.dumps({'status': 'credential_probe_succeeded', 'request_run': RUN}), flush=True)
    print(json.dumps({'recovered_retry_jobs': recovered}), flush=True)
    await run_setlist_queue(verified_after)


async def run_setlist_queue(verified_after):
    processed = 0
    while True:
        result = await music_jobs.run_once(kinds=('youtube_collect',), request_run=RUN,
            worker_name=RUN, rate_limit_observed_after=verified_after)
        if result['status'] == 'idle':
            summary = await asyncio.to_thread(backfill.status)
            if not any(row['status'] in ('pending', 'retry', 'running') for row in summary['jobs']):
                print(json.dumps({'status': 'finished', 'processed': processed, 'summary': summary}, default=str), flush=True)
                return
            await asyncio.sleep(30)
            continue
        processed += 1
        print(json.dumps(result), flush=True)
        if result['status'] == 'retry':
            job = await music_jobs.status(result['id'])
            if job and job['last_error'] == 'rate_limited':
                print(json.dumps({'status': 'stopped_on_rate_limit', 'summary': await asyncio.to_thread(backfill.status)}, default=str), flush=True)
                return
            # Retry timing and attempt limits remain controlled by the job queue.
            print(json.dumps({'status': 'retry_scheduled', 'id': result['id'],
                              'error': job['last_error'] if job else None}), flush=True)
        await asyncio.sleep(1)


def recover_request_retries(session, verified_after):
    """Explicitly reschedule only this request's older quota failures."""
    verify_catalog_identity(session)
    return list(session.execute(text("""UPDATE worker_jobs SET next_attempt_at=clock_timestamp()
        WHERE job_type='youtube_collect' AND payload->>'request_run'=:run
        AND status='retry' AND last_error='rate_limited' AND updated_at<:verified
        RETURNING id"""), {'run': RUN, 'verified': verified_after}).scalars())


def skip_missing_setlists(write=False):
    with Session(catalog_engine(catalog_url())) as session, session.begin():
        if not write:
            session.execute(text('SET TRANSACTION READ ONLY'))
        verify_catalog_identity(session)
        rows = session.execute(text("""SELECT j.id job_id,v.platform_video_id video_id,l.id archive_id,v.title
            FROM worker_jobs j JOIN videos v ON v.platform='youtube' AND v.platform_video_id=j.payload->>'youtube_video_id'
            JOIN live_archives l ON l.video_id=v.id JOIN artists a ON a.id=l.primary_artist_id
            WHERE j.job_type='youtube_collect' AND j.payload->>'request_run'=:run
            AND j.status IN ('pending','retry') AND a.slug=:slug
            AND l.archived_at IS NULL AND l.setlist_state='unprocessed'
            AND NOT EXISTS (SELECT 1 FROM performances p WHERE p.archive_id=l.id AND p.archived_at IS NULL)
            ORDER BY j.id"""), {'run': RUN, 'slug': SLUG}).mappings().all()
        cancelled = []
        if write:
            for row in rows:
                if worker_jobs.cancel(session, row['job_id']):
                    cancelled.append(row['job_id'])
    result = {'request_run': RUN, 'candidate_jobs': len(rows), 'cancelled_jobs': cancelled,
              'broadcasts': [dict(row) for row in rows], 'reason': 'user_requested_skip_missing_setlists'}
    if write:
        REPORT.mkdir(parents=True, exist_ok=True)
        (REPORT / 'skipped-missing-setlists.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('register', 'plan', 'enqueue', 'worker', 'status', 'verify', 'broadcasts', 'resume-setlists', 'skip-missing-setlists'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    # The retained backfill functions resolve these module-level request inputs.
    backfill.RUN = RUN
    backfill.targets = targets
    registration.POLICY = RUN + '-registration-v1'
    if args.command == 'skip-missing-setlists':
        result = skip_missing_setlists(args.apply)
        print(json.dumps({key: value for key, value in result.items() if key != 'broadcasts'}))
    elif args.command == 'resume-setlists':
        asyncio.run(resume_setlists())
    elif args.command == 'broadcasts':
        print(json.dumps(asyncio.run(save_broadcasts(args.apply))))
    elif args.command == 'register':
        items = [item for item, _ in targets()]
        with psycopg.connect(load_connection(), connect_timeout=20) as conn:
            configure_transaction(conn, read_only=not args.apply)
            result = registration.register(conn, items, write=args.apply)
            if args.apply:
                result['aliases_created'] = register_aliases(conn, items)
            if not args.apply:
                conn.rollback()
        print(json.dumps(result, ensure_ascii=False, default=str))
    elif args.command == 'enqueue' and args.apply:
        backfill.enqueue(0)
    elif args.command == 'verify':
        with Session(catalog_engine(catalog_url())) as session:
            session.execute(text('SET TRANSACTION READ ONLY'))
            verify_catalog_identity(session)
            artist_id = session.execute(text("SELECT id FROM artists WHERE slug=:slug AND archived_at IS NULL"), {'slug': SLUG}).scalar_one()
            holds = session.execute(text("SELECT job_type,count(*) count,max(next_attempt_at) resume_at FROM worker_jobs WHERE status='retry' AND last_error='rate_limited' AND next_attempt_at>clock_timestamp() GROUP BY job_type")).mappings().all()
            archives = session.execute(text("SELECT l.setlist_state,count(*) count FROM live_archives l JOIN artists a ON a.id=l.primary_artist_id WHERE a.slug=:slug AND l.archived_at IS NULL GROUP BY l.setlist_state"), {'slug': SLUG}).mappings().all()
            setlists = session.execute(text("""SELECT count(DISTINCT l.id) FILTER (WHERE p.id IS NOT NULL) archives_with_setlist,
                count(p.id) performances FROM live_archives l JOIN artists a ON a.id=l.primary_artist_id
                LEFT JOIN performances p ON p.archive_id=l.id AND p.archived_at IS NULL
                WHERE a.slug=:slug AND l.archived_at IS NULL"""), {'slug': SLUG}).mappings().one()
            session.rollback()
        from app.api.main import app
        headers = {'X-API-Key': settings.api_key} if settings.api_key else {}
        with TestClient(app) as client:
            artists = client.get('/api/artists', headers=headers)
            artists.raise_for_status()
            artist = next(a for a in artists.json() if a['id'] == artist_id)
            lives = client.get(f"/api/artists/{artist['id']}/lives", headers=headers)
            lives.raise_for_status()
            page = lives.json()
            detail = None
            if page['items']:
                response = client.get(f"/api/lives/{page['items'][0]['id']}", headers=headers)
                response.raise_for_status()
                detail = {'http_status': response.status_code, 'id': page['items'][0]['id']}
        print(json.dumps({'artist_id': artist['id'], 'display_name': artist['display_name'],
                         'lives': {'total': page['total'], 'returned': len(page['items'])}, 'detail': detail,
                         'archive_states': [dict(r) for r in archives], 'setlists': dict(setlists),
                         'provider_holds': [dict(r) for r in holds]}, default=str))
    elif args.command == 'worker':
        asyncio.run(backfill.worker())
    else:
        print(json.dumps(backfill.status() if args.command == 'status' else backfill.plan(), default=str))


if __name__ == '__main__':
    main()
