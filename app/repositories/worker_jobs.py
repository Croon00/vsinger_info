"""Durable music jobs. Every write belongs to the caller's transaction."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.schemas.worker_jobs import JobRequest, Payload, PAYLOAD_MODELS, account_identity


class JobConflict(ValueError):
    pass


class LeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    id: int
    job_type: str
    external_account_id: int
    video_id: int | None
    payload: dict
    attempt_count: int
    max_attempts: int
    lease_owner: str


def validate_account(session: Session, request: JobRequest, payload: Payload) -> None:
    platform, external_id = account_identity(request.job_type, payload)
    account = session.execute(text('''
        SELECT id FROM external_accounts WHERE id=:id AND platform=:platform
          AND platform_id=:external_id AND collection_enabled AND archived_at IS NULL
        FOR SHARE
    '''), dict(id=request.external_account_id, platform=platform,
               external_id=external_id)).scalar_one_or_none()
    if account is None:
        raise JobConflict('Account is missing, disabled, archived, or its platform ID differs')
    if request.video_id is not None:
        if request.job_type != 'youtube_collect':
            raise JobConflict('Only youtube_collect may reference a video')
        valid = session.execute(text('''
            SELECT id FROM videos WHERE id=:id AND platform='youtube'
              AND platform_video_id=:external_id AND archived_at IS NULL
              AND (source_account_id IS NULL OR source_account_id=:account)
        '''), dict(id=request.video_id, external_id=payload.youtube_video_id,
                   account=request.external_account_id)).scalar_one_or_none()
        if valid is None:
            raise JobConflict('Video reference does not match the account and external video ID')


def enqueue(session: Session, request: JobRequest, *, due_at: datetime | None = None) -> int:
    payload = request.parsed_payload()
    validate_account(session, request, payload)
    key = request.key()
    job_id = session.execute(text('''
        INSERT INTO worker_jobs(job_type,idempotency_key,external_account_id,video_id,
                                payload,max_attempts,next_attempt_at)
        VALUES (:kind,:key,:account,:video,CAST(:payload AS jsonb),:attempts,:due)
        ON CONFLICT (job_type,idempotency_key) DO NOTHING RETURNING id
    '''), dict(kind=request.job_type, key=key, account=request.external_account_id,
               video=request.video_id, payload=json.dumps(payload.model_dump()),
               attempts=request.max_attempts, due=due_at)).scalar_one_or_none()
    if job_id is not None:
        return int(job_id)
    existing = session.execute(text('''
        SELECT id,external_account_id,video_id,payload,max_attempts FROM worker_jobs
        WHERE job_type=:kind AND idempotency_key=:key
    '''), dict(kind=request.job_type, key=key)).mappings().one()
    if (existing['external_account_id'] != request.external_account_id
            or existing['video_id'] != request.video_id
            or existing['payload'] != payload.model_dump()
            or existing['max_attempts'] != request.max_attempts):
        raise JobConflict('Existing job has a different contract; use an explicit new request_run')
    return int(existing['id'])


def claim(session: Session, kinds: tuple[str, ...], *, owner: str, lease_seconds: float,
          min_interval_seconds: float = 1) -> Job | None:
    if not kinds:
        return None
    if set(kinds) - set(PAYLOAD_MODELS):
        raise ValueError('Unsupported music job types')
    available = []
    for platform, lock_id in (('youtube', 941201), ('spotify', 941202)):
        selected = [kind for kind in kinds if kind.startswith(platform + '_')]
        if selected and session.execute(text('SELECT pg_try_advisory_xact_lock(:key)'),
                                        {'key': lock_id}).scalar_one():
            available.extend(selected)
    if not available:
        return None
    params = dict(kinds=tuple(available), interval=max(0, min_interval_seconds))
    # Only handle registered job types; unimplemented/legacy jobs stay untouched.
    session.execute(text('''
        UPDATE worker_jobs SET status=CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retry' END,
          finished_at=CASE WHEN attempt_count >= max_attempts THEN clock_timestamp() ELSE NULL END,
          lease_owner=NULL,lease_expires_at=NULL,next_attempt_at=clock_timestamp(),
          last_error='worker lease expired'
        WHERE job_type IN :kinds AND status='running' AND lease_expires_at <= clock_timestamp()
    ''').bindparams(bindparam('kinds', expanding=True)), params)
    session.execute(text('''
        UPDATE worker_jobs j SET status='cancelled',finished_at=clock_timestamp(),
          next_attempt_at=NULL,last_error='account unavailable'
        WHERE job_type IN :kinds AND status IN ('pending','retry')
          AND NOT EXISTS (
            SELECT 1 FROM external_accounts a WHERE a.id=j.external_account_id
              AND a.collection_enabled AND a.archived_at IS NULL
              AND a.platform=CASE WHEN j.job_type='spotify_collect' THEN 'spotify' ELSE 'youtube' END)
    ''').bindparams(bindparam('kinds', expanding=True)), params)
    session.execute(text('''
        UPDATE worker_jobs SET status='failed',finished_at=clock_timestamp(),next_attempt_at=NULL,
          last_error='attempt limit reached'
        WHERE job_type IN :kinds AND status IN ('pending','retry') AND attempt_count >= max_attempts
    ''').bindparams(bindparam('kinds', expanding=True)), params)
    row = session.execute(text('''
        SELECT j.* FROM worker_jobs j JOIN external_accounts a ON a.id=j.external_account_id
        WHERE j.job_type IN :kinds AND j.status IN ('pending','retry')
          AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= clock_timestamp())
          AND a.collection_enabled AND a.archived_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM worker_jobs busy
            WHERE split_part(busy.job_type,'_',1)=a.platform AND busy.attempt_count > 0
              AND ((busy.status='running' AND busy.lease_expires_at > clock_timestamp())
                   OR busy.updated_at > clock_timestamp()-(:interval * interval '1 second')))
        ORDER BY j.next_attempt_at NULLS FIRST,j.id
        FOR UPDATE OF j SKIP LOCKED LIMIT 1
    ''').bindparams(bindparam('kinds', expanding=True)), params).mappings().one_or_none()
    if row is None:
        return None
    session.execute(text('''
        UPDATE worker_jobs SET status='running',attempt_count=attempt_count+1,
          lease_owner=:owner,lease_expires_at=clock_timestamp()+(:seconds * interval '1 second'),
          finished_at=NULL,last_error=NULL WHERE id=:id
    '''), dict(id=row['id'], owner=owner, seconds=lease_seconds))
    return Job(int(row['id']), row['job_type'], row['external_account_id'], row['video_id'],
               row['payload'], row['attempt_count'] + 1, row['max_attempts'], owner)


def renew(session: Session, job: Job, *, lease_seconds: float) -> bool:
    result = session.execute(text('''
        UPDATE worker_jobs j SET lease_expires_at=clock_timestamp()+(:seconds * interval '1 second')
        WHERE j.id=:id AND j.status='running' AND j.lease_owner=:owner
          AND j.lease_expires_at > clock_timestamp()
          AND EXISTS (SELECT 1 FROM external_accounts a WHERE a.id=j.external_account_id
                      AND a.collection_enabled AND a.archived_at IS NULL)
    '''), dict(id=job.id, owner=job.lease_owner, seconds=lease_seconds))
    return result.rowcount == 1


def lock_current(session: Session, job: Job, payload: Payload) -> None:
    found = session.execute(text('''
        SELECT id FROM worker_jobs WHERE id=:id AND status='running' AND lease_owner=:owner
          AND lease_expires_at > clock_timestamp() FOR UPDATE
    '''), dict(id=job.id, owner=job.lease_owner)).scalar_one_or_none()
    if found is None:
        raise LeaseLost('Job claim no longer belongs to this worker')
    validate_account(session, JobRequest(job_type=job.job_type,
                     external_account_id=job.external_account_id,video_id=job.video_id,
                     payload=job.payload,max_attempts=job.max_attempts), payload)


def complete(session: Session, job: Job) -> None:
    result = session.execute(text('''
        UPDATE worker_jobs SET status='succeeded',finished_at=clock_timestamp(),next_attempt_at=NULL,
          lease_owner=NULL,lease_expires_at=NULL,last_error=NULL
        WHERE id=:id AND status='running' AND lease_owner=:owner
          AND lease_expires_at > clock_timestamp()
    '''), dict(id=job.id, owner=job.lease_owner))
    if result.rowcount != 1:
        raise LeaseLost('Job lease expired before result commit')


def fail(session: Session, job: Job, *, error: str, retry: bool, delay: float = 30) -> bool:
    retry = retry and job.attempt_count < job.max_attempts
    result = session.execute(text('''
        UPDATE worker_jobs SET status=:status,last_error=:error,
          next_attempt_at=CASE WHEN :retry THEN clock_timestamp()+(:delay * interval '1 second') ELSE NULL END,
          finished_at=CASE WHEN :retry THEN NULL ELSE clock_timestamp() END,
          lease_owner=NULL,lease_expires_at=NULL
        WHERE id=:id AND status='running' AND lease_owner=:owner
          AND lease_expires_at > clock_timestamp()
    '''), dict(id=job.id, owner=job.lease_owner, status='retry' if retry else 'failed',
               error=error, retry=retry, delay=max(0, delay)))
    return result.rowcount == 1


def cancel(session: Session, job_id: int) -> bool:
    return session.execute(text('''
        UPDATE worker_jobs SET status='cancelled',finished_at=clock_timestamp(),next_attempt_at=NULL,
          lease_owner=NULL,lease_expires_at=NULL,last_error='cancelled by explicit request'
        WHERE id=:id AND status IN ('pending','retry','running')
          AND job_type IN ('youtube_poll','youtube_collect','spotify_collect')
    '''), dict(id=job_id)).rowcount == 1


def get_job(session: Session, job_id: int) -> dict | None:
    row = session.execute(text('''
        SELECT id,job_type,status,external_account_id,video_id,attempt_count,max_attempts,
          next_attempt_at,lease_expires_at,finished_at,last_error,created_at,updated_at
        FROM worker_jobs WHERE id=:id
    '''), dict(id=job_id)).mappings().one_or_none()
    return dict(row) if row else None


def queue_status(session: Session) -> dict:
    rows = session.execute(text('''
        SELECT job_type,status,count(*) AS count FROM worker_jobs GROUP BY job_type,status
        ORDER BY job_type,status
    ''')).mappings().all()
    summary = session.execute(text('''
        SELECT count(*) FILTER (WHERE status IN ('pending','retry') AND
                 (next_attempt_at IS NULL OR next_attempt_at <= clock_timestamp())) AS due,
          count(*) FILTER (WHERE status='running' AND lease_expires_at > clock_timestamp()) AS live_leases,
          max(finished_at) FILTER (WHERE status='succeeded') AS last_success_at,
          max(updated_at) FILTER (WHERE status IN ('failed','retry')) AS last_failure_at
        FROM worker_jobs
    ''')).mappings().one()
    return dict(counts=[dict(row) for row in rows], **dict(summary))


def active_account_counts(session: Session) -> dict[str, int]:
    rows = session.execute(text('''SELECT platform,count(*) AS count FROM external_accounts
        WHERE platform IN ('youtube','spotify') AND collection_enabled AND archived_at IS NULL
        GROUP BY platform''')).mappings().all()
    return {row['platform']: row['count'] for row in rows}


def note_polled(session: Session, job: Job, *, interval_seconds: float):
    session.execute(text('''
        INSERT INTO collection_states(external_account_id,last_polled_at,next_poll_at)
        VALUES (:id,clock_timestamp(),clock_timestamp()+(:interval * interval '1 second'))
        ON CONFLICT (external_account_id) DO UPDATE
          SET last_polled_at=EXCLUDED.last_polled_at,next_poll_at=EXCLUDED.next_poll_at
    '''), {'id': job.external_account_id, 'interval': interval_seconds})


def schedule_youtube_polls(session: Session, *, interval_seconds: float = 86400,
                           limit: int = 100) -> int:
    """Queue one due poll per registered channel; a handler must opt into scheduling."""
    session.execute(text('''
        INSERT INTO collection_states(external_account_id)
        SELECT id FROM external_accounts WHERE platform='youtube' AND collection_enabled
          AND archived_at IS NULL ON CONFLICT DO NOTHING
    '''))
    rows = session.execute(text('''
        SELECT a.id,a.platform_id,cs.next_poll_at FROM external_accounts a
        JOIN collection_states cs ON cs.external_account_id=a.id
        WHERE a.platform='youtube' AND a.collection_enabled AND a.archived_at IS NULL
          AND a.platform_id ~ '^UC[A-Za-z0-9_-]{22}$'
          AND (cs.next_poll_at IS NULL OR cs.next_poll_at <= clock_timestamp())
          AND NOT EXISTS (SELECT 1 FROM worker_jobs j WHERE j.external_account_id=a.id
                          AND j.job_type='youtube_poll' AND j.status IN ('pending','retry','running'))
        ORDER BY cs.next_poll_at NULLS FIRST,a.id FOR UPDATE OF cs SKIP LOCKED LIMIT :limit
    '''), {'limit': limit}).mappings().all()
    for row in rows:
        run = row['next_poll_at'].isoformat() if row['next_poll_at'] else 'initial'
        enqueue(session, JobRequest(job_type='youtube_poll', external_account_id=row['id'],
                payload={'channel_id': row['platform_id'], 'request_run': run}))
        session.execute(text('''
            UPDATE collection_states SET next_poll_at=clock_timestamp()+(:interval * interval '1 second')
            WHERE external_account_id=:id
        '''), {'id': row['id'], 'interval': max(1, interval_seconds)})
    return len(rows)
