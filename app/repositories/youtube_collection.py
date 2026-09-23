"""Normalized YouTube persistence. All writes share the claimed job transaction."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.repositories import worker_jobs
from app.schemas.worker_jobs import JobRequest


def poll_state(session, account):
    result = session.execute(text('SELECT provider_state,last_polled_at FROM collection_states WHERE external_account_id=:id'),
                             {'id': account}).mappings().one_or_none()
    return dict(result) if result else {'provider_state': {}, 'last_polled_at': None}


def snapshot(session, video_id, *, lock=False):
    video = session.execute(text("SELECT id,version,source_account_id,archived_at FROM videos WHERE platform='youtube' AND platform_video_id=:id" +
                                 (' FOR UPDATE' if lock else '')), {'id': video_id}).mappings().one_or_none()
    if video is None:
        return {'video': None, 'archive': None, 'cover': None}
    result = {'video': dict(video)}
    for key, table in (('archive', 'live_archives'), ('cover', 'covers')):
        columns = 'id,version,archived_at,setlist_state' if table == 'live_archives' else 'id,version,archived_at'
        value = session.execute(text(f'SELECT {columns} FROM {table} WHERE video_id=:id' + (' FOR UPDATE' if lock else '')),
                                {'id': video['id']}).mappings().one_or_none()
        result[key] = dict(value) if value else None
    return result


def persist_poll(session, job, payload, value):
    state = value['state']['provider_state']
    baseline = state.get('youtube_baseline_at')
    if not payload.backfill_video_ids:
        baseline = baseline or value['captured_at'].isoformat()
        pending = [v.id for v in value['videos'] if not v.ended_at and (v.started_at or v.scheduled)]
        # Merge our namespace only; preserve migration and other runtime metadata.
        session.execute(text('''INSERT INTO collection_states(external_account_id,provider_state)
            VALUES (:id,CAST(:state AS jsonb)) ON CONFLICT (external_account_id) DO UPDATE
            SET provider_state=collection_states.provider_state || EXCLUDED.provider_state'''),
            {'id': job.external_account_id, 'state': json.dumps({
                'youtube_baseline_at': baseline, 'youtube_uploads_playlist': value['playlist'],
                'youtube_window_truncated': value['truncated'],
                'youtube_poll_gap': bool(state.get('youtube_poll_gap')) or value['gap'] or len(pending) > 200,
                'youtube_pending_video_ids': pending[:200],
            })})
    for video in value['videos']:
        kind = value['purposes'].get(video.id)
        if not kind:
            continue
        if not payload.backfill_video_ids:
            observed = video.ended_at if kind == 'archive' else video.published_at
            if observed is None or observed < datetime.fromisoformat(baseline):
                continue
        due = video.ended_at + timedelta(hours=24) if kind == 'archive' else None
        if not payload.backfill_video_ids and session.execute(text('''SELECT EXISTS (
            SELECT 1 FROM worker_jobs WHERE job_type='youtube_collect'
              AND external_account_id=:account AND payload->>'youtube_video_id'=:video
              AND payload->>'purpose'=:purpose)'''),
              dict(account=job.external_account_id, video=video.id, purpose=kind)).scalar_one():
            continue
        worker_jobs.enqueue(session, JobRequest(job_type='youtube_collect', external_account_id=job.external_account_id,
            payload={'channel_id': payload.channel_id, 'youtube_video_id': video.id, 'purpose': kind,
                     'request_run': payload.request_run if payload.backfill_video_ids else 'initial'}), due_at=due)


def _document(session, *, video_id, kind, external_id, content, metadata, disposition, captured_at):
    # Capture time/disposition are observations, not source identity. Same raw source
    # and extractor output is immutable and deduplicated even after manual edits.
    canonical = json.dumps(dict(kind=kind, external_id=external_id, content=content, metadata=metadata),
                           sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    existing = session.execute(text('SELECT id FROM source_documents WHERE content_hash=:hash ORDER BY id LIMIT 1'),
                               {'hash': digest}).scalar_one_or_none()
    if existing:
        return existing, False
    from urllib.parse import quote
    url = f'https://www.youtube.com/watch?v={video_id}'
    if kind == 'youtube_comment':
        url += '&lc=' + quote(external_id, safe='')
    document = session.execute(text('''INSERT INTO source_documents(source_kind,source_url,external_id,captured_at,
            content_text,content_hash,source_metadata)
        VALUES (:kind,:url,:external,:captured,:content,:hash,CAST(:metadata AS jsonb)) RETURNING id'''),
        dict(kind=kind, url=url, external=external_id, captured=captured_at, content=content or None, hash=digest,
             metadata=json.dumps({**metadata, 'disposition': disposition}, ensure_ascii=False))).scalar_one()
    return document, True


def persist_collect(session, job, payload, value):
    # Serializes absent-row inserts too. Account/lease were revalidated by the runner.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:id, 941203))'), {'id': payload.youtube_video_id})
    current = snapshot(session, payload.youtube_video_id, lock=True)
    conflict = current != value['snapshot'] or any(v and v['archived_at'] for v in current.values())
    existing = current['video']
    if existing and existing['source_account_id'] not in (None, job.external_account_id):
        raise worker_jobs.JobConflict('Video belongs to a different source account')
    video, outcome = value['video'], value['outcome']
    video_id = existing['id'] if existing else None
    if video_id is None and video is not None and not conflict:
        video_id = session.execute(text('''INSERT INTO videos(platform,platform_video_id,source_account_id,title,
            published_at,duration_seconds,availability) VALUES ('youtube',:external,:account,:title,:published,:duration,:availability) RETURNING id'''),
            dict(external=video.id, account=job.external_account_id, title=video.title, published=video.published_at,
                 duration=video.duration_seconds, availability=video.availability)).scalar_one()
    archive_id = current['archive']['id'] if current['archive'] else None
    new_archive = False
    if (payload.purpose == 'archive' and video_id and not conflict and not archive_id and not current['cover']
            and outcome not in ('waiting', 'not_due', 'not_eligible')):
        owners = session.execute(text('''SELECT a.id FROM artist_external_accounts e JOIN artists a ON a.id=e.artist_id
            WHERE e.account_id=:account AND e.relationship='owner' AND a.archived_at IS NULL ORDER BY e.position,a.id'''),
            {'account': job.external_account_id}).scalars().all()
        archive_id = session.execute(text('''INSERT INTO live_archives(video_id,primary_artist_id,broadcast_at,setlist_state)
            VALUES (:video,:artist,:broadcast,:state) RETURNING id'''),
            dict(video=video_id, artist=owners[0] if len(owners) == 1 else None,
                 broadcast=video.started_at if video else None,
                 state='partial' if value['rows'] else 'unavailable')).scalar_one()
        for position, artist in enumerate(owners):
            session.execute(text("INSERT INTO archive_artists(archive_id,artist_id,role,position) VALUES (:archive,:artist,'host',:position)"),
                            dict(archive=archive_id, artist=artist, position=position))
        new_archive = True
    resume_archive = False
    if (archive_id and current['archive'] and not conflict and payload.purpose == 'archive'
            and value['rows'] and current['archive']['setlist_state'] in ('unprocessed', 'unavailable', 'partial')):
        resume_archive = bool(session.execute(text('''UPDATE live_archives SET setlist_state='partial'
            WHERE id=:id AND version=:version AND archived_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM performances WHERE archive_id=:id AND archived_at IS NULL)
            RETURNING id'''), dict(id=archive_id, version=current['archive']['version'])).scalar_one_or_none())
    disposition = 'version_conflict' if conflict else ('applied' if new_archive or resume_archive else 'review_candidate')
    metadata = dict(collector='youtube-catalog', video_id=payload.youtube_video_id, outcome=outcome,
                    video=video.model_dump(mode='json') if video else None,
                    extraction_version=payload.extraction_version, extractor=value['extractor'], rows=value['rows'],
                    comments_truncated=value.get('comments_truncated', False), attribution='unresolved')
    comment = value.get('comment')
    document, _ = _document(session, video_id=payload.youtube_video_id,
        kind='youtube_comment' if comment else 'video_description', external_id=comment.id if comment else payload.youtube_video_id,
        content=comment.text if comment else (video.description if video else ''), metadata=metadata,
        disposition=disposition, captured_at=comment.captured_at if comment else value['captured_at'])
    if archive_id and not conflict:
        session.execute(text('''INSERT INTO archive_sources(archive_id,document_id,role) VALUES (:archive,:document,:role)
            ON CONFLICT DO NOTHING'''), dict(archive=archive_id, document=document, role='setlist_evidence' if comment else 'metadata_evidence'))
    if new_archive or resume_archive:
        for ordinal, entry in enumerate(value['rows'], 1):
            session.execute(text('''INSERT INTO performances(archive_id,ordinal,start_seconds,raw_title,raw_artist,raw_timestamp,source_document_id)
                VALUES (:archive,:ordinal,:seconds,:title,:artist,:stamp,:document)'''),
                dict(archive=archive_id, ordinal=ordinal, seconds=entry['start_seconds'], title=entry['title'],
                     artist=entry.get('original_artist') or None, stamp=entry['timestamp'], document=document))
    if (payload.purpose == 'cover' and outcome == 'collected' and video_id and not conflict
            and not current['archive'] and not current['cover']):
        session.execute(text('INSERT INTO covers(video_id) VALUES (:id) ON CONFLICT DO NOTHING'), {'id': video_id})
        # A channel owner is not proof of vocal participation. Credits remain in
        # the immutable description until explicit artist evidence is approved.
    if outcome in ('waiting', 'not_due') and not conflict and payload.wait_count < 168:
        next_payload = payload.model_dump()
        next_payload['wait_count'] += 1
        worker_jobs.enqueue(session, JobRequest(job_type='youtube_collect', external_account_id=job.external_account_id,
            video_id=job.video_id, payload=next_payload, max_attempts=job.max_attempts),
            due_at=value.get('due_at') or datetime.now(UTC) + timedelta(hours=1))
