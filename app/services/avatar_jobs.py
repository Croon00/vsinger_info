"""Independent initial-avatar worker; registration and read API never do network I/O."""
import asyncio
import logging
from uuid import uuid4

import httpx
from PIL import Image

from app.integrations.avatar_sources import discover, AvatarSourceError, AvatarCandidate, retry_delay
from app.repositories import avatar_jobs as repository
from app.services import avatar_storage
from app.services.music_jobs import db_call
from app.services.worker_wait import wait_for_work

logger = logging.getLogger(__name__)


async def prepare_image(job):
    # Preserve an already-selected provider when an upload needs retrying.
    selected = job.get('result', {})
    if 'source_url' in selected:
        candidate = AvatarCandidate.model_validate(selected)
        data = await asyncio.to_thread(avatar_storage.download, candidate.source_url)
        generated = await asyncio.to_thread(avatar_storage.variants, data)
        return candidate, data, generated, selected.get('failures', [])
    failures = []
    provider_attempts = dict(job.get('result', {}).get('provider_attempts', {}))
    for account in job['sources']:
        key = str(account['id'])
        if provider_attempts.get(key, 0) >= 3:
            failures.append({'account_id': account['id'], 'code': 'provider_retries_exhausted'})
            continue
        try:
            candidate = await discover(account)
            data = await asyncio.to_thread(avatar_storage.download, candidate.source_url)
            try:
                generated = await asyncio.to_thread(avatar_storage.variants, data)
            except (ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                failures.append({'account_id': account['id'], 'code': 'invalid_image'})
                continue
            return candidate, data, generated, failures
        except AvatarSourceError as exc:
            failures.append({'account_id': account['id'], 'code': exc.code})
            if exc.retry:
                provider_attempts[key] = provider_attempts.get(key, 0) + 1
            if exc.retry and provider_attempts[key] < 3 and job['attempt_count'] < job['max_attempts']:
                exc.failures = failures
                exc.provider_attempts = provider_attempts
                exc.platform = account['platform']
                raise
        except httpx.HTTPStatusError as exc:
            failures.append({'account_id': account['id'], 'code': 'image_http_error'})
            retry = exc.response.status_code == 429 or exc.response.status_code >= 500
            if retry:
                provider_attempts[key] = provider_attempts.get(key, 0) + 1
            if retry and provider_attempts[key] < 3 and job['attempt_count'] < job['max_attempts']:
                error = AvatarSourceError('image_http_error', retry=True, retry_after=retry_delay(exc.response))
                error.failures = failures
                error.provider_attempts = provider_attempts
                error.platform = account['platform']
                raise error from None
        except (httpx.RequestError, OSError):
            provider_attempts[key] = provider_attempts.get(key, 0) + 1
            if provider_attempts[key] < 3 and job['attempt_count'] < job['max_attempts']:
                error = AvatarSourceError('image_download_failed', retry=True)
                error.failures = failures + [{'account_id': account['id'], 'code': error.code}]
                error.provider_attempts = provider_attempts
                error.platform = account['platform']
                raise error from None
            failures.append({'account_id': account['id'], 'code': 'image_download_failed'})
        except ValueError:
            failures.append({'account_id': account['id'], 'code': 'invalid_image'})
    return None, None, None, failures


async def _heartbeat(job):
    while True:
        await asyncio.sleep(30)
        if not await db_call(repository.renew, job):
            raise RuntimeError('avatar_lease_lost')


async def _process(job):
    state = await db_call(repository.current, job)
    if state:
        return await db_call(repository.finish, job, state)
    try:
        candidate, data, generated, failures = await prepare_image(job)
    except AvatarSourceError as exc:
        return await db_call(repository.fail, job, code=exc.code, retry=exc.retry,
            delay=exc.retry_after or 60, result={'failures': getattr(exc, 'failures', []),
                'provider_attempts': getattr(exc, 'provider_attempts', {}),
                'retry_platform': getattr(exc, 'platform', None)})
    except Exception:
        return await db_call(repository.fail, job, code='image_prepare_failed', retry=True, result=job.get('result'))
    if candidate is None:
        return await db_call(repository.finish, job, 'no_source', {'failures': failures})
    prefix = avatar_storage.image_prefix(job['artist_id'], data, generated)
    result = {**candidate.model_dump(), 'prefix': prefix, 'failures': failures}
    try:
        new_url = await asyncio.to_thread(avatar_storage.upload, prefix, data, generated)
    except Exception as exc:
        # Upload failure never changes provider preference or the artist's image.
        error = avatar_storage.storage_error(exc, stage='storage')
        result['storage_error'] = error.details
        logger.warning('Avatar storage failed: job_id=%s artist_id=%s attempt=%s error=%s',
                       job['id'], job['artist_id'], job['attempt_count'], error.details)
        return await db_call(repository.fail, job, code='avatar_storage_failed', retry=True, result=result)
    result['new_url'] = new_url
    return await db_call(repository.finish, job, 'succeeded', result)


async def run_once(*, artist_ids=None):
    if not await db_call(repository.available):
        return {'status': 'migration_required'}
    job = await db_call(repository.claim, owner='avatar-' + str(uuid4()), artist_ids=artist_ids)
    if job is None:
        return {'status': 'idle'}
    heartbeat = asyncio.create_task(_heartbeat(job))
    work = asyncio.create_task(asyncio.wait_for(_process(job), timeout=240))
    try:
        done, _ = await asyncio.wait((heartbeat, work), return_when=asyncio.FIRST_COMPLETED)
        if heartbeat in done:
            heartbeat.result()
        return {'job_id': job['id'], 'artist_id': job['artist_id'], 'status': await work}
    except Exception:
        status = await db_call(repository.fail, job, code='avatar_worker_failed', retry=True)
        return {'job_id': job['id'], 'status': status}
    finally:
        for task in (heartbeat, work):
            if not task.done():
                task.cancel()
        await asyncio.gather(heartbeat, work, return_exceptions=True)


async def avatar_worker_loop(*, artist_ids=None):
    logger.info('Avatar worker started: artist_scope=%s', artist_ids)
    previous = None
    while True:
        busy = False
        try:
            result = await run_once(artist_ids=artist_ids)
            if result['status'] != 'idle' and (result['status'] != 'migration_required' or previous != result['status']):
                logger.info('Avatar job: %s', result)
            previous = result['status']
            busy = result['status'] not in ('idle', 'migration_required')
        except Exception:
            logger.error('Avatar worker failed')
        await wait_for_work(seconds=5 if busy else None)
