"""Independent discovery (30 min) and known stream checks (1 min), no LLM/notify."""
import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import settings
from app.db.catalog_session import catalog_runtime_session
from app.integrations.youtube_catalog import YouTubeClient, YouTubeFailure
from app.integrations.holodex import HolodexClient, HolodexFailure
from app.repositories import youtube_live_monitor as repository

logger = logging.getLogger(__name__)


async def db_call(function, *args, **kwargs):
    def transact():
        with catalog_runtime_session() as session:
            return function(session, *args, **kwargs)
    task = asyncio.create_task(asyncio.to_thread(transact))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Do not leave a commit in flight when the monitor is stopped.
        await task
        raise


def valid_ids(values):
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', v)))[:200]


async def run_once(provider=None):
    token = str(uuid4())
    accounts = await db_call(repository.claim, token)
    result = dict(accounts=len(accounts), live=0, scheduled=0, failed=0)
    if not accounts:
        return result
    provider = provider or YouTubeClient(settings.youtube_api_key)
    captured = datetime.now(UTC)
    try:
        async with asyncio.timeout(150):
            ids = set()
            ready = []
            for account in accounts:
                state = account['state']
                known = valid_ids(state.get('candidate_ids', []) + account['pending'])
                account['check_ids'] = known
                if account['discover']:
                    try:
                        playlist, recent = await provider.discover_live_ids(
                            account['channel_id'], state.get('playlist') or account['playlist'])
                    except YouTubeFailure as exc:
                        if exc.retry_after:
                            raise
                        logger.warning('Live discovery deferred for account %s: %s', account['id'], exc.reason)
                        await db_call(repository.defer, token, account_id=account['id'], seconds=600)
                        result['failed'] += 1
                        continue
                    account['playlist'], account['recent_ids'] = playlist, recent
                    # Normal uploads already checked are remembered to save quota.
                    account['check_ids'] = valid_ids(known + [id for id in recent if id not in state.get('recent_ids', [])])
                ids.update(account['check_ids'])
                ready.append(account)
            videos = await provider.videos(sorted(ids)) if ids else []
            by_id = {v.id: v for v in videos}
            for account in ready:
                candidates = [by_id[id] for id in account['check_ids'] if id in by_id
                    and by_id[id].channel_id == account['channel_id'] and by_id[id].availability == 'public'
                    and not by_id[id].ended_at and (by_id[id].started_at or by_id[id].scheduled)]
                streams = [dict(video_id=v.id, title=v.title, started_at=v.started_at.isoformat())
                           for v in candidates if v.started_at]
                upcoming = [dict(video_id=v.id, title=v.title,
                                 scheduled_at=v.scheduled_at.isoformat() if v.scheduled_at else None)
                            for v in candidates if not v.started_at]
                state = {k: v for k, v in account['state'].items()
                         if k not in ('lease_token', 'lease_until', 'retry_at')}
                state.update(candidate_ids=[v.id for v in candidates],
                             next_check_at=(captured+timedelta(seconds=settings.youtube_live_check_seconds)).isoformat())
                if account['discover']:
                    state.update(playlist=account['playlist'], recent_ids=account['recent_ids'],
                        next_discovery_at=(captured+timedelta(seconds=settings.youtube_live_discovery_seconds)).isoformat())
                saved = await db_call(repository.save, account, token, state,
                    dict(checked_at=captured.isoformat(), streams=streams, upcoming=upcoming))
                if saved:
                    result['live'] += len(streams)
                    result['scheduled'] += sum(not v.started_at for v in candidates)
                else:
                    result['failed'] += 1
    except YouTubeFailure as exc:
        await db_call(repository.defer, token, seconds=max(60, exc.retry_after),
                      all_accounts=bool(exc.retry_after))
        result['failed'] = len(accounts)
        # Provider reasons are sanitized; request URLs/credentials never reach logs.
        logger.warning('Live monitor deferred: %s', exc.reason)
    except BaseException:
        await db_call(repository.defer, token)
        raise
    return result


async def run_holodex_once(provider=None):
    token = str(uuid4())
    accounts = await db_call(repository.claim_holodex, token)
    result = dict(accounts=len(accounts), live=0, scheduled=0, failed=0)
    if not accounts:
        return result
    try:
        async with asyncio.timeout(150):
            provider = provider or HolodexClient(settings.holodex_api_key)
            videos = await provider.live([a['channel_id'] for a in accounts])
            captured = datetime.now(UTC)
            by_channel = {}
            for video in videos:
                by_channel.setdefault(video.channel_id, []).append(video)
            updates = []
            for account in accounts:
                candidates = by_channel.get(account['channel_id'], [])
                streams = [dict(video_id=v.id, title=v.title,
                    started_at=v.start_actual.isoformat() if v.start_actual else None)
                    for v in candidates if v.status == 'live']
                upcoming = [dict(video_id=v.id, title=v.title,
                    scheduled_at=v.start_scheduled.isoformat() if v.start_scheduled else None)
                    for v in candidates if v.status == 'upcoming']
                state = dict(next_check_at=(captured+timedelta(seconds=settings.holodex_poll_seconds)).isoformat())
                updates.append(dict(id=account['id'], channel_id=account['channel_id'], state=state,
                    snapshot=dict(provider='holodex', checked_at=captured.isoformat(), streams=streams, upcoming=upcoming)))
            saved = await db_call(repository.save_holodex_batch, token, updates)
            for update in updates:
                if update['id'] in saved:
                    result['live'] += len(update['snapshot']['streams'])
                    result['scheduled'] += len(update['snapshot']['upcoming'])
                else:
                    result['failed'] += 1
    except HolodexFailure as exc:
        await db_call(repository.defer, token, seconds=exc.retry_after,
                      all_accounts=True, namespace='holodex_live_monitor')
        result['failed'] = len(accounts)
        logger.warning('Holodex live monitor deferred: %s', exc.reason)
    except BaseException:
        await db_call(repository.defer, token, namespace='holodex_live_monitor')
        raise
    return result


async def monitor_loop():
    # httpx INFO request URLs contain the provider API key query parameter.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    if not (settings.holodex_api_key or settings.youtube_api_key):
        logger.warning('Live monitor is disabled: missing Holodex and YouTube API keys')
        return
    while True:
        try:
            result = await (run_holodex_once() if settings.holodex_api_key else run_once())
            if result['accounts']:
                logger.info('%s live monitor: %s', 'Holodex' if settings.holodex_api_key else 'YouTube', result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('Live monitor failed: %s', type(exc).__name__)
            await asyncio.sleep(30)
        # Independent of the archive worker's 15-minute idle wait. DB leases
        # ensure another instance cannot claim the same channels concurrently.
        await asyncio.sleep(5)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(monitor_loop())
