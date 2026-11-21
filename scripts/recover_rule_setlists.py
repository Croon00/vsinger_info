"""Audit empty archives and recover only rule-verified stored comments. No model calls."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import text
from app.db.catalog_session import get_catalog_session, catalog_runtime_session
from app.integrations.youtube_catalog import Comment, Video
from app.repositories import worker_jobs, youtube_collection as repository
from app.schemas.worker_jobs import JobRequest
from app.services.youtube_setlist import POLICY, shortlist, context_for
from app.services.youtube_setlist_rules import RULE_POLICY, choose_rules
from app.services import music_jobs

RUN = 'rules-recovery-2026-11-21'
VERSION = 'numbered-rules-20261121'


def load():
    sessions = get_catalog_session()
    session = next(sessions)
    try:
        rows = [dict(r) for r in session.execute(text('''
            SELECT l.id archive_id,l.primary_artist_id artist_id,a.name_native,a.name_ko,
              v.id video_id,v.platform_video_id,v.duration_seconds,v.availability,e.id account_id,e.platform_id channel_id,
              e.collection_enabled,e.archived_at account_archived_at,
              EXISTS(SELECT 1 FROM performances p WHERE p.archive_id=l.id) protected_performances
            FROM live_archives l JOIN videos v ON v.id=l.video_id
            JOIN artists a ON a.id=l.primary_artist_id
            LEFT JOIN external_accounts e ON e.id=v.source_account_id AND e.platform='youtube'
            WHERE l.archived_at IS NULL AND v.archived_at IS NULL AND a.archived_at IS NULL
              AND a.show_in_catalog AND NOT EXISTS(
                SELECT 1 FROM performances p WHERE p.archive_id=l.id AND p.archived_at IS NULL)
            ORDER BY (v.platform_video_id='dSszoaOjZiY') DESC,
              (a.id IN (1041,1046,1045,1044)) DESC,l.broadcast_at DESC NULLS LAST,l.id
        ''')).mappings()]
        documents = [dict(r) for r in session.execute(text('''
            SELECT DISTINCT ON (ars.archive_id,d.external_id) ars.archive_id,d.id,
              d.external_id,d.content_text,d.captured_at,d.source_metadata
            FROM archive_sources ars JOIN source_documents d ON d.id=ars.document_id
            JOIN live_archives l ON l.id=ars.archive_id
            WHERE l.archived_at IS NULL AND d.source_kind='youtube_comment'
              AND NOT EXISTS(SELECT 1 FROM performances p WHERE p.archive_id=l.id)
            ORDER BY ars.archive_id,d.external_id,d.id DESC
        ''')).mappings()]
    finally:
        sessions.close()
    grouped = defaultdict(list)
    for document in documents:
        grouped[document['archive_id']].append(document)
    return rows, grouped


def evaluate(row, documents):
    if row['protected_performances']:
        return None, 'protected_archived_performances'
    if not row['account_id'] or not row['collection_enabled'] or row['account_archived_at']:
        return None, 'account_unavailable'
    if row['availability'] not in ('public', 'unlisted', 'unknown'):
        return None, 'video_unavailable'
    comments = [Comment(id=d['external_id'], text=d['content_text'], captured_at=d['captured_at'])
                for d in documents if d['external_id'] and d['content_text'] and d['captured_at']]
    if not comments:
        return None, 'no_stored_comments'
    candidates = shortlist(comments)
    index, parsed = choose_rules([context_for(c['comment']) for c in candidates], row['duration_seconds'])
    if index is None:
        return None, 'needs_more_rules_or_review'
    sources = [d for d in documents if d['source_metadata'].get('video')]
    if not sources:
        return None, 'no_stored_video_metadata'
    video = Video.model_validate(max(sources, key=lambda d: d['id'])['source_metadata']['video'])
    if video.id != row['platform_video_id'] or video.channel_id != row['channel_id']:
        return None, 'stored_identity_conflict'
    for rank, (candidate, result) in enumerate(zip(candidates, parsed), 1):
        candidate.update(rank=rank, context_truncated=False, rule_reason=result.reason)
    selection = dict(policy=POLICY, method='rules', rule_policy=RULE_POLICY, status='selected',
                     considered_count=len(comments), retained_count=len(candidates), comparison_calls=0,
                     validation_error=None, retry_after_seconds=0, model_result=None,
                     recovery_run=RUN, rule_reason=parsed[index].reason)
    return dict(video=video, candidates=candidates, comment=candidates[index]['comment'],
                rows=parsed[index].rows, selection=selection), 'rules_selected'


def persist(row, selected):
    request = JobRequest(job_type='youtube_collect', external_account_id=row['account_id'],
                         video_id=row['video_id'], payload=dict(channel_id=row['channel_id'],
                         youtube_video_id=row['platform_video_id'], purpose='archive', request_run=RUN,
                         extraction_version=VERSION, wait_count=168, selection_retry_count=2))
    payload = request.parsed_payload()
    with catalog_runtime_session() as session:
        # Source identity and archive state are checked again within the write
        # transaction. Existing active OR archived performances are preserved.
        archive = session.execute(text('SELECT id FROM live_archives WHERE id=:id AND archived_at IS NULL FOR UPDATE'),
                                  {'id': row['archive_id']}).scalar_one_or_none()
        if archive is None or session.execute(text('SELECT 1 FROM performances WHERE archive_id=:id LIMIT 1'),
                                             {'id': row['archive_id']}).first():
            return {'archive_id': row['archive_id'], 'status': 'preserved_existing'}
        job_id = worker_jobs.enqueue(session, request)
        claimed = session.execute(text('''UPDATE worker_jobs SET status='running',attempt_count=attempt_count+1,
            lease_owner=:owner,lease_expires_at=clock_timestamp()+interval '5 minutes',
            finished_at=NULL,last_error=NULL WHERE id=:id AND status IN ('pending','retry')
            AND attempt_count<max_attempts AND (next_attempt_at IS NULL OR next_attempt_at<=clock_timestamp())
            RETURNING *'''), {'id': job_id, 'owner': RUN + '-' + str(uuid4())}).mappings().one_or_none()
        if claimed is None:
            return {'archive_id': row['archive_id'], 'job_id': job_id, 'status': 'already_processed_or_busy'}
        job = worker_jobs.Job(claimed['id'], claimed['job_type'], claimed['external_account_id'],
                             claimed['video_id'], claimed['payload'], claimed['attempt_count'],
                             claimed['max_attempts'], claimed['lease_owner'])
        snapshot = repository.snapshot(session, row['platform_video_id'], lock=True)
        if not snapshot['archive'] or snapshot['archive']['id'] != row['archive_id']:
            raise ValueError('Archive source identity changed')
        value = dict(snapshot=snapshot, captured_at=datetime.now(UTC), outcome='collected',
                     extractor=RULE_POLICY, **selected)
        handler = music_jobs.Handler(lambda *_: None, repository.persist_collect)
        music_jobs._persist(session, job, payload, value, handler)
        count = session.execute(text('SELECT count(*) FROM performances WHERE archive_id=:id AND archived_at IS NULL'),
                                {'id': row['archive_id']}).scalar_one()
        return {'archive_id': row['archive_id'], 'artist_id': row['artist_id'], 'video_id': row['platform_video_id'],
                'job_id': job_id, 'status': 'recovered' if count else 'review_candidate',
                'songs': count, 'rule_reason': selected['selection']['rule_reason']}


async def main(args):
    rows, documents = load()
    if args.video:
        rows = [row for row in rows if row['platform_video_id'] == args.video]
    if args.artist:
        rows = [row for row in rows if row['artist_id'] in args.artist]
    counts, by_artist, eligible, plan = Counter(), defaultdict(Counter), [], []
    for row in rows:
        selected, reason = evaluate(row, documents[row['archive_id']])
        counts[reason] += 1
        by_artist[row['artist_id']][reason] += 1
        plan.append({**row, 'reason': reason, 'songs': len(selected['rows']) if selected else 0})
        if selected:
            eligible.append((row, selected))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    summary = {'run': RUN, 'rule_policy': RULE_POLICY, 'empty_archives': len(rows),
               'artists': len(by_artist), 'audit': dict(counts), 'model_calls': 0,
               'eligible_songs': sum(len(value['rows']) for _, value in eligible),
               'by_artist': {str(key): dict(value) for key, value in by_artist.items()}}
    print(json.dumps({k: v for k, v in summary.items() if k != 'by_artist'}), flush=True)
    if args.apply:
        semaphore = asyncio.Semaphore(args.workers)
        results = []
        async def process(row, value):
            async with semaphore:
                try:
                    result = await asyncio.to_thread(persist, row, value)
                except Exception as exc:
                    result = {'archive_id': row['archive_id'], 'status': 'failed', 'error_type': type(exc).__name__}
                results.append(result)
                with (args.output / 'outcomes.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(result) + '\n')
                if len(results) % 25 == 0 or result['status'] == 'failed':
                    print(json.dumps({'processed': len(results), 'total': len(eligible),
                                      'results': dict(Counter(r['status'] for r in results))}), flush=True)
        await asyncio.gather(*(process(row, value) for row, value in eligible))
        summary.update(results=dict(Counter(r['status'] for r in results)),
                       recovered_songs=sum(r.get('songs', 0) for r in results))
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--video')
    parser.add_argument('--artist', type=int, action='append')
    parser.add_argument('--workers', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs' / RUN)
    asyncio.run(main(parser.parse_args()))
