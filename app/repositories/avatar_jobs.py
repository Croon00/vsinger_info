"""Initial avatar queue. SQL stays in short identity-guarded transactions."""
import hashlib
import json
from uuid import UUID, uuid5

from sqlalchemy import text

NAMESPACE = UUID('e4e7a9b8-9fb3-4d4e-b9ab-f79c6a9d56cd')


def available(session):
    return session.execute(text("SELECT to_regclass('public.avatar_jobs') IS NOT NULL")).scalar_one()


def enqueue(session, artist_id, request_run='automatic'):
    return session.execute(text('SELECT avatar_enqueue(:id,:run)'), {'id': artist_id, 'run': request_run}).scalar_one()


def preview(session, artist_ids):
    return [dict(row) for row in session.execute(text('''SELECT id,name_native,avatar_url,
        archived_at,avatar_sources(id) sources FROM artists WHERE id=ANY(:ids) ORDER BY id'''),
        {'ids': artist_ids}).mappings()]


def get_job(session, job_id):
    row = session.execute(text('SELECT * FROM avatar_jobs WHERE id=:id'), {'id': job_id}).mappings().one_or_none()
    return dict(row) if row else None


def claim(session, *, owner, lease_seconds=300):
    session.execute(text('''UPDATE avatar_jobs SET status='failed',last_error='lease_exhausted',
        finished_at=clock_timestamp(),lease_owner=NULL,lease_expires_at=NULL,updated_at=clock_timestamp()
        WHERE status='running' AND lease_expires_at<=clock_timestamp() AND attempt_count>=max_attempts'''))
    row = session.execute(text('''SELECT * FROM avatar_jobs
        WHERE attempt_count<max_attempts AND ((status IN ('pending','retry') AND
          (next_attempt_at IS NULL OR next_attempt_at<=clock_timestamp())) OR
          (status='running' AND lease_expires_at<=clock_timestamp()))
        AND NOT EXISTS (SELECT 1 FROM avatar_jobs busy WHERE busy.artist_id=avatar_jobs.artist_id
          AND busy.status='running' AND busy.lease_expires_at>clock_timestamp())
        AND NOT EXISTS (SELECT 1 FROM avatar_jobs cooldown WHERE cooldown.status='retry'
          AND cooldown.next_attempt_at>clock_timestamp() AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(avatar_jobs.sources) candidate
            WHERE candidate->>'platform'=cooldown.result->>'retry_platform'))
        ORDER BY next_attempt_at NULLS FIRST,id FOR UPDATE SKIP LOCKED LIMIT 1''')).mappings().one_or_none()
    if row is None:
        return None
    # Serialize claims for different snapshots of the same artist, including different workers.
    session.execute(text('SELECT id FROM artists WHERE id=:id FOR UPDATE'), {'id': row['artist_id']})
    if session.execute(text('''SELECT EXISTS(SELECT 1 FROM avatar_jobs WHERE artist_id=:artist
        AND status='running' AND lease_expires_at>clock_timestamp())'''), {'artist': row['artist_id']}).scalar_one():
        return None
    return dict(session.execute(text('''UPDATE avatar_jobs SET status='running',attempt_count=attempt_count+1,
        lease_owner=:owner,lease_expires_at=clock_timestamp()+(:seconds*interval '1 second'),
        updated_at=clock_timestamp() WHERE id=:id RETURNING *'''),
        {'id': row['id'], 'owner': owner, 'seconds': lease_seconds}).mappings().one())


def renew(session, job, lease_seconds=300):
    return session.execute(text('''UPDATE avatar_jobs SET lease_expires_at=clock_timestamp()+(:seconds*interval '1 second')
        WHERE id=:id AND status='running' AND lease_owner=:owner AND lease_expires_at>clock_timestamp()'''),
        {'id': job['id'], 'owner': job['lease_owner'], 'seconds': lease_seconds}).rowcount == 1


def current(session, job):
    row = session.execute(text('''SELECT avatar_url,archived_at,avatar_sources(id) sources
        FROM artists WHERE id=:id FOR UPDATE'''), {'id': job['artist_id']}).mappings().one_or_none()
    if not row or row['archived_at'] is not None:
        return 'conflict'
    if row['avatar_url'] is not None:
        return 'skipped_existing'
    if row['sources'] != job['sources']:
        return 'conflict'
    return None


def finish(session, job, status, result=None):
    locked = session.execute(text('''SELECT id FROM avatar_jobs WHERE id=:id AND status='running'
        AND lease_owner=:owner AND lease_expires_at>clock_timestamp() FOR UPDATE'''),
        {'id': job['id'], 'owner': job['lease_owner']}).scalar_one_or_none()
    if locked is None:
        return 'lease_lost'
    result = result or {}
    if status == 'succeeded':
        status = current(session, job) or status
        if status == 'succeeded':
            before = dict(session.execute(text('SELECT * FROM artists WHERE id=:id'),
                {'id': job['artist_id']}).mappings().one())
            after = dict(session.execute(text('''UPDATE artists SET avatar_url=:url,updated_at=clock_timestamp()
                WHERE id=:id RETURNING *'''), {'id': job['artist_id'], 'url': result['new_url']}).mappings().one())
            body = json.dumps(result, sort_keys=True, default=str)
            import_id = session.execute(text('''INSERT INTO catalog_imports(operation_id,catalog_instance_id,
                manifest_hash,source_kind,result_mapping,result_summary)
                SELECT :op,id,:digest,'manual','[]'::jsonb,CAST(:summary AS jsonb) FROM catalog_instance RETURNING id'''),
                {'op': uuid5(NAMESPACE, str(job['id'])), 'digest': hashlib.sha256(body.encode()).hexdigest(),
                 'summary': json.dumps({'kind': 'initial-avatar-v1', 'job_id': job['id'], 'artist_id': job['artist_id']})}).scalar_one()
            session.execute(text('''INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,
                before_data,after_data,provenance) VALUES (:import,'artists',:artist,'update',
                CAST(:before AS jsonb),CAST(:after AS jsonb),CAST(:provenance AS jsonb))'''),
                {'import': import_id, 'artist': job['artist_id'], 'before': json.dumps(before, default=str),
                 'after': json.dumps(after, default=str), 'provenance': body})
    session.execute(text('''UPDATE avatar_jobs SET status=:status,result=CAST(:result AS jsonb),
        finished_at=clock_timestamp(),next_attempt_at=NULL,lease_owner=NULL,lease_expires_at=NULL,
        last_error=NULL,updated_at=clock_timestamp() WHERE id=:id'''),
        {'id': job['id'], 'status': status, 'result': json.dumps(result)})
    return status


def fail(session, job, *, code, retry, delay=60, result=None):
    retry = retry and job['attempt_count'] < job['max_attempts']
    changed = session.execute(text('''UPDATE avatar_jobs SET status=:status,last_error=:error,result=CAST(:result AS jsonb),
        next_attempt_at=CASE WHEN :retry THEN clock_timestamp()+(:delay*interval '1 second') ELSE NULL END,
        finished_at=CASE WHEN :retry THEN NULL ELSE clock_timestamp() END,
        lease_owner=NULL,lease_expires_at=NULL,updated_at=clock_timestamp()
        WHERE id=:id AND status='running' AND lease_owner=:owner AND lease_expires_at>clock_timestamp()'''),
        {'id': job['id'], 'owner': job['lease_owner'], 'status': 'retry' if retry else 'failed',
         'error': code[:100], 'retry': retry, 'delay': max(30, delay), 'result': json.dumps(result or {})})
    return ('retry' if retry else 'failed') if changed.rowcount == 1 else 'lease_lost'
