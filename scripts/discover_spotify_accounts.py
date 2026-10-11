"""Explicit exact-name discovery and audited registration for missing Spotify links.

Default: provider search + read-only DB report. --apply registers unique matches
and queues the existing discography worker in one transaction. No read endpoint
performs discovery. Ambiguous, truncated and previously rejected identities wait.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.catalog_session import catalog_engine, catalog_url, verify_catalog_identity
from app.integrations.spotify_catalog import SpotifyCatalogClient, SpotifyFailure
from app.repositories.worker_jobs import enqueue
from app.schemas.worker_jobs import JobRequest
from app.services.spotify_discovery import artist_names, decide

POLICY = 'spotify-unique-exact-name-v1'


def snapshot(session):
    identity = verify_catalog_identity(session)
    artists = [dict(r) for r in session.execute(text("""SELECT a.id,a.version,a.name_native,a.name_latin,a.name_ko
        FROM artists a WHERE a.archived_at IS NULL AND a.show_in_catalog AND NOT EXISTS (
        SELECT 1 FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
        WHERE ae.artist_id=a.id AND e.platform='spotify' AND e.archived_at IS NULL) ORDER BY a.id""")).mappings()]
    occupied = set(session.execute(text("SELECT platform_id FROM external_accounts WHERE platform='spotify'")).scalars())
    return identity, artists, occupied


def rejected_ids():
    file = ROOT / 'migrations/catalog/spotify-account-decisions-1.json'
    rejected = set()
    if file.exists():
        for item in json.loads(file.read_text(encoding='utf-8'))['items']:
            if item.get('decision') == 'skip':
                if item.get('spotify_id'):
                    rejected.add(item['spotify_id'])
                for candidate in item.get('alternatives', []):
                    if isinstance(candidate, dict) and candidate.get('spotify_id'):
                        rejected.add(candidate['spotify_id'])
    return rejected


def previously_skipped_artists():
    file = ROOT / 'migrations/catalog/spotify-account-decisions-1.json'
    if not file.exists():
        return set()
    return {item['artist_id'] for item in json.loads(file.read_text(encoding='utf-8'))['items']
            if item.get('decision') == 'skip'}


async def research(artists, occupied, output, *, direct=False):
    provider = SpotifyCatalogClient(settings.spotify_client_id or '', settings.spotify_client_secret or '',
        transport=httpx.AsyncHTTPTransport() if direct else None)
    cache_file = output / 'search-cache.json'
    cache = json.loads(cache_file.read_text(encoding='utf-8')) if cache_file.exists() else {}
    results = []
    rejected = rejected_ids()
    skipped_artists = previously_skipped_artists()
    for artist in artists:
        candidates, complete = [], True
        try:
            for name in artist_names(artist):
                if name not in cache:
                    items, finished = await provider.search_artists(name)
                    cache[name] = dict(items=items, complete=finished)
                    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
                candidates.extend(cache[name]['items'])
                complete = complete and cache[name]['complete']
            result = decide(artist, candidates, complete=complete, occupied_ids=occupied, rejected_ids=rejected)
            if result['status'] == 'match' and artist['id'] in skipped_artists:
                result.update(status='review', reason='previous_identity_review_requires_recheck')
        except SpotifyFailure as exc:
            result = dict(artist_id=artist['id'], artist_name=artist['name_native'],
                          status='error', reason=str(exc), retry_after=exc.retry_after)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            # A provider outage/rate limit applies to the batch; do not hammer it.
            break
        results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k!='candidates'}, ensure_ascii=False), flush=True)
    counts = Counter(r.get('spotify_id') for r in results if r['status'] == 'match')
    for result in results:
        if result['status'] == 'match' and counts[result['spotify_id']] > 1:
            result.update(status='review', reason='shared_candidate_between_catalog_artists')
    return results


def apply(session, report, *, run_label):
    identity = verify_catalog_identity(session)
    if identity != report['catalog_instance_id']:
        raise ValueError('Catalog identity changed')
    revisions = set(session.execute(text('SELECT version FROM catalog_schema_migrations')).scalars())
    if '006' not in revisions:
        raise ValueError('Provider credit migration 006 required')
    session.execute(text('SELECT pg_advisory_xact_lock(731064924)'))
    session.execute(text('SELECT pg_advisory_xact_lock(731064925)'))
    matches = [r for r in report['items'] if r['status'] == 'match']
    if any(r['artist_id'] in previously_skipped_artists() for r in matches):
        raise ValueError('Prior identity review must be resolved before registering')
    if len({r['spotify_id'] for r in matches}) != len(matches):
        raise ValueError('A discovered account cannot acquire multiple owners')
    if not matches:
        return dict(registered=0, jobs=[])
    digest = hashlib.sha256(json.dumps(matches, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    operation = str(uuid5(NAMESPACE_URL, identity + ':' + POLICY + ':' + digest))
    existing = session.execute(text('SELECT id FROM catalog_imports WHERE operation_id=:op'), dict(op=operation)).scalar_one_or_none()
    if existing:
        return dict(status='already_applied', receipt_id=existing)
    changes, mapping, jobs = [], [], []
    for match in matches:
        artist = session.execute(text('SELECT version,archived_at,show_in_catalog FROM artists WHERE id=:id FOR UPDATE'), dict(id=match['artist_id'])).mappings().one()
        if artist['version'] != match['artist_version'] or artist['archived_at'] or not artist['show_in_catalog']:
            raise ValueError('Artist changed since discovery')
        if session.execute(text("SELECT 1 FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id WHERE ae.artist_id=:id AND e.platform='spotify' AND e.archived_at IS NULL"), dict(id=match['artist_id'])).first():
            raise ValueError('Artist already linked since discovery')
        if session.execute(text("SELECT 1 FROM external_accounts WHERE platform='spotify' AND platform_id=:id"), dict(id=match['spotify_id'])).first():
            raise ValueError('Spotify account already registered; preserve ownership')
        account = dict(session.execute(text("INSERT INTO external_accounts(platform,platform_id,url,collection_enabled) VALUES ('spotify',:sid,:url,true) RETURNING *"),dict(sid=match['spotify_id'],url='https://open.spotify.com/artist/'+match['spotify_id'])).mappings().one())
        position = session.execute(text('SELECT coalesce(max(position),-1)+1 FROM artist_external_accounts WHERE artist_id=:id'),dict(id=match['artist_id'])).scalar_one()
        link = dict(session.execute(text("INSERT INTO artist_external_accounts(artist_id,account_id,relationship,is_primary,position) VALUES (:artist,:account,'owner',true,:position) RETURNING *"),dict(artist=match['artist_id'],account=account['id'],position=position)).mappings().one())
        for table, value in (('external_accounts',account),('artist_external_accounts',link)):
            changes.append((table,value,match))
            mapping.append(dict(entity_type=table,id=value['id']))
        jobs.append(enqueue(session,JobRequest(job_type='spotify_collect',external_account_id=account['id'],payload=dict(spotify_artist_id=match['spotify_id'],request_run=run_label,link_youtube=False))))
    receipt = session.execute(text("INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary) VALUES (:op,:instance,:hash,'manual',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id"),dict(op=operation,instance=identity,hash=digest,mapping=json.dumps(mapping),summary=json.dumps(dict(policy=POLICY,registered=len(matches),jobs=jobs)))).scalar_one()
    for table,value,match in changes:
        session.execute(text("INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,after_data,provenance) VALUES (:receipt,:table,:id,'create',CAST(:after AS jsonb),CAST(:provenance AS jsonb))"),dict(receipt=receipt,table=table,id=value['id'],after=json.dumps(value,default=str),provenance=json.dumps(dict(policy=POLICY,basis=match['reason'],spotify_name=match['spotify_name'],candidates=match['candidates'],authority='user_requested_exact_name_criterion',reviewed=False),ensure_ascii=False)))
    return dict(registered=len(matches),jobs=jobs,receipt_id=receipt)


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--direct-connect',action='store_true',help='Ignore environment proxy for provider requests')
    parser.add_argument('--run',default='spotify-discovery-'+datetime.now(UTC).strftime('%Y-%m-%d'))
    parser.add_argument('--output',type=Path,required=True,help='Use a fresh directory for each new discovery batch')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    engine=catalog_engine(catalog_url())
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        session.execute(text("SET LOCAL statement_timeout='20s'"))
        identity,artists,occupied=snapshot(session)
    items=await research(artists,occupied,args.output,direct=args.direct_connect)
    report=dict(policy=POLICY,catalog_instance_id=identity,created_at=datetime.now(UTC).isoformat(),target_count=len(artists),items=items)
    (args.output/'candidates.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.apply:
        with Session(engine) as session,session.begin():
            session.execute(text("SET LOCAL lock_timeout='10s'"))
            report['application']=apply(session,report,run_label=args.run)
        (args.output/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(targets=len(artists),processed=len(items),statuses=dict(Counter(r['status'] for r in items)),application=report.get('application')),ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
