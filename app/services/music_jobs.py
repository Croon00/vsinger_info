"""Independent runner for read-only provider collection and atomic local persistence.

Production YouTube handlers are registered below. An empty registry must never
claim jobs or report unimplemented work as successful.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DisconnectionError, TimeoutError as DatabaseTimeout

from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session, verify_catalog_identity
from app.repositories import worker_jobs as repository
from app.schemas.worker_jobs import JobRequest, PAYLOAD_MODELS, Payload

logger = logging.getLogger(__name__)


class RetryableJobError(Exception):
    def __init__(self, *, retry_after: float = 0):
        self.retry_after = max(0, retry_after)


class PermanentJobError(Exception):
    pass


@dataclass(frozen=True)
class Handler:
    # collect must not write to a DB or perform externally visible side effects.
    collect: Callable[[repository.Job, Payload], Awaitable[Any]]
    persist: Callable[[Session, repository.Job, Payload, Any], None]
    timeout_seconds: float = 120
    poll_interval_seconds: float = 86400

    def __post_init__(self):
        if self.timeout_seconds <= 0 or self.poll_interval_seconds <= 0:
            raise ValueError('Handler timing must be positive')


HANDLERS: dict[str, Handler] = {}
WORKER_HEALTH: dict[str, dict] = {}


async def db_call(function, *args, **kwargs):
    """Run short transactions off the event loop; drain an in-flight commit on shutdown."""
    def transact():
        with catalog_runtime_session() as session:
            return function(session, *args, **kwargs)
    task = asyncio.create_task(asyncio.to_thread(transact))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancelled:
        try:
            await task
        except Exception:
            pass
        raise cancelled


async def enqueue(request: JobRequest) -> int:
    return await db_call(repository.enqueue, request)


async def status(job_id: int) -> dict | None:
    return await db_call(repository.get_job, job_id)


async def cancel(job_id: int) -> bool:
    return await db_call(repository.cancel, job_id)


async def readiness() -> dict:
    def inspect(session):
        identity = verify_catalog_identity(session)
        return {'database_verified': True, 'instance_id': identity,
                'queue': repository.queue_status(session),
                'active_accounts': repository.active_account_counts(session)}
    result = await db_call(inspect)
    result['registered_handlers'] = sorted(HANDLERS)
    result['unimplemented_handlers'] = sorted(set(PAYLOAD_MODELS) - set(HANDLERS))
    result['local_workers'] = {key: dict(value) for key, value in WORKER_HEALTH.items()}
    return result


def _persist(session, job, payload, value, handler):
    repository.lock_current(session, job, payload)
    handler.persist(session, job, payload, value)
    if job.job_type == 'youtube_poll' and not payload.backfill_video_ids:
        repository.note_polled(session, job, interval_seconds=handler.poll_interval_seconds)
    repository.complete(session, job)


async def _heartbeat(job, lease_seconds, health):
    while True:
        await asyncio.sleep(lease_seconds / 3)
        if not await db_call(repository.renew, job, lease_seconds=lease_seconds):
            raise repository.LeaseLost('Heartbeat lost job ownership')
        health['heartbeat_at'] = datetime.now(UTC).isoformat()


async def _record_failure(job, exc, retry, delay=30):
    try:
        return await db_call(repository.fail, job, error=type(exc).__name__, retry=retry, delay=delay)
    except Exception:
        # No provider side effect occurred. The lease sweeper recovers after DB recovery.
        logger.error('Could not record failure for music job %s', job.id)
        return False


async def run_once(*, handlers: dict[str, Handler] | None = None,
                   kinds: tuple[str, ...] | None = None, lease_seconds: float = 90,
                   min_interval_seconds: float = 1, worker_name: str = 'music') -> dict:
    handlers = HANDLERS if handlers is None else handlers
    if set(handlers) - set(PAYLOAD_MODELS):
        raise ValueError('Unsupported music handler')
    if lease_seconds <= 0:
        raise ValueError('Lease duration must be positive')
    enabled = tuple(kind for kind in (tuple(handlers) if kinds is None else kinds) if kind in handlers)
    health = WORKER_HEALTH.setdefault(worker_name, {})
    health.update(heartbeat_at=datetime.now(UTC).isoformat(), state='idle')
    health.pop('error', None)
    if not enabled:
        health['state'] = 'waiting_for_handler'
        return {'status': 'waiting_for_handler'}
    job = await db_call(repository.claim, enabled, owner=f'{worker_name}-{uuid4()}',
                        lease_seconds=lease_seconds, min_interval_seconds=min_interval_seconds)
    if job is None:
        return {'status': 'idle'}
    health.update(state='running', job_id=job.id)
    heartbeat = None
    work = None
    try:
        payload = PAYLOAD_MODELS[job.job_type].model_validate(job.payload)
        await db_call(repository.lock_current, job, payload)
        handler = handlers[job.job_type]
        heartbeat = asyncio.create_task(_heartbeat(job, lease_seconds, health))
        work = asyncio.create_task(asyncio.wait_for(handler.collect(job, payload), handler.timeout_seconds))
        done, _ = await asyncio.wait((heartbeat, work), return_when=asyncio.FIRST_COMPLETED)
        if heartbeat in done:
            await heartbeat
        value = await work
        if not await db_call(repository.renew, job, lease_seconds=lease_seconds):
            raise repository.LeaseLost('Claim changed before persistence')
        await db_call(_persist, job, payload, value, handler)
        health['last_success_at'] = datetime.now(UTC).isoformat()
        return {'id': job.id, 'status': 'succeeded'}
    except asyncio.CancelledError as exc:
        # Shutdown is resumable; explicit cancel already fenced the job in the DB.
        await _record_failure(job, exc, True, delay=0)
        raise
    except repository.LeaseLost:
        return {'id': job.id, 'status': 'lease_lost'}
    except Exception as exc:
        retry = isinstance(exc, (RetryableJobError, TimeoutError, OperationalError,
                                 DisconnectionError, DatabaseTimeout))
        delay = max(getattr(exc, 'retry_after', 0), min(3600, 30 * 2 ** min(job.attempt_count - 1, 7)))
        updated = await _record_failure(job, exc, retry, delay)
        health['last_failure_at'] = datetime.now(UTC).isoformat()
        return {'id': job.id, 'status': ('retry' if retry and job.attempt_count < job.max_attempts else 'failed')
                if updated else 'lease_lost'}
    finally:
        for task in (heartbeat, work):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (heartbeat, work) if task is not None), return_exceptions=True)
        health.update(state='idle', heartbeat_at=datetime.now(UTC).isoformat(), job_id=None)


async def _provider_loop(platform: str):
    name = f'music-{platform}'
    try:
        while True:
            try:
                kinds = tuple(kind for kind in HANDLERS if kind.startswith(platform + '_'))
                if 'youtube_poll' in kinds:
                    await db_call(repository.schedule_youtube_polls,
                                  interval_seconds=HANDLERS['youtube_poll'].poll_interval_seconds)
                result = await run_once(kinds=kinds, worker_name=name)
                if result['status'] not in ('idle', 'waiting_for_handler'):
                    logger.info('Music job outcome: %s', result)
            except Exception as exc:
                WORKER_HEALTH.setdefault(name, {}).update(
                    state='error', heartbeat_at=datetime.now(UTC).isoformat(),
                    last_failure_at=datetime.now(UTC).isoformat(), error=type(exc).__name__)
                logger.error('Music worker %s failed (%s)', platform, type(exc).__name__)
            await asyncio.sleep(5)
    finally:
        WORKER_HEALTH.setdefault(name, {})['state'] = 'stopped'


async def music_worker_loop():
    if not (settings.runtime_cutover_enabled and settings.agent_enabled):
        return
    async with asyncio.TaskGroup() as group:
        group.create_task(_provider_loop('youtube'))
        group.create_task(_provider_loop('spotify'))


# Registration has no DB/network side effects.
from app.services.youtube_collection import handlers as youtube_handlers
from app.services.spotify_collection import handlers as spotify_handlers
HANDLERS.update(youtube_handlers())
HANDLERS.update(spotify_handlers())
