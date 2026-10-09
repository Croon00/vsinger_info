"""Idle scheduling regressions: no real DB or provider calls."""
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import worker_wait, music_jobs, avatar_jobs, worker_readiness
from app.agents import scheduler
from app.services.notification_delivery import DeliveryResult
from app.services.x_collection import CollectionResult


def test_idle_checks_align_across_workers(monkeypatch):
    monkeypatch.setattr(worker_wait.settings, 'worker_idle_seconds', 900)
    monkeypatch.setattr(worker_wait.time, 'time', lambda: 1000)
    assert worker_wait.idle_delay() == 800
    monkeypatch.setattr(worker_wait.time, 'time', lambda: 1800)
    assert worker_wait.idle_delay() == 900


def test_idle_wait_maintains_memory_heartbeat(monkeypatch):
    async def scenario():
        clock = [0.0]
        sleeps = []
        health = {'state': 'idle', 'heartbeat_at': 'old'}
        monkeypatch.setattr(worker_wait.asyncio, 'get_running_loop',
                            lambda: SimpleNamespace(time=lambda: clock[0]))
        async def sleep(seconds):
            sleeps.append(seconds)
            assert health['heartbeat_at'] != 'old'
            clock[0] += seconds
        monkeypatch.setattr(worker_wait.asyncio, 'sleep', sleep)
        await worker_wait.wait_for_work(seconds=900, health=health)
        assert sum(sleeps) == 900 and max(sleeps) <= 30
        assert health['state'] == 'idle'
    asyncio.run(scenario())


def test_wakeup_interrupts_idle_wait_and_cancellation_propagates():
    async def scenario():
        wake = asyncio.Event()
        task = asyncio.create_task(worker_wait.wait_for_work(seconds=900, wake=wake))
        await asyncio.sleep(0)
        wake.set()
        await asyncio.wait_for(task, 1)
        task = asyncio.create_task(worker_wait.wait_for_work(seconds=900))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())


@pytest.mark.parametrize('platform', ['youtube', 'spotify'])
@pytest.mark.parametrize('status,delay', [('idle', None), ('succeeded', 5)])
def test_music_idle_backs_off_but_busy_queue_drains(monkeypatch, platform, status, delay):
    run = AsyncMock(return_value={'status': status})
    schedule = AsyncMock()
    wait = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(music_jobs, 'run_once', run)
    monkeypatch.setattr(music_jobs, 'db_call', schedule)
    monkeypatch.setattr(music_jobs, 'wait_for_work', wait)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(music_jobs._provider_loop(platform))
    assert wait.call_args.kwargs['seconds'] == delay
    assert schedule.await_count == (1 if platform == 'youtube' else 0)
    assert music_jobs.WORKER_HEALTH['music-' + platform]['state'] == 'stopped'


def test_busy_youtube_does_not_reschedule_every_job(monkeypatch):
    monkeypatch.setattr(music_jobs, 'run_once', AsyncMock(return_value={'status': 'succeeded'}))
    schedule = AsyncMock()
    monkeypatch.setattr(music_jobs, 'db_call', schedule)
    monkeypatch.setattr(music_jobs, 'idle_delay', lambda: 900)
    monkeypatch.setattr(music_jobs, 'wait_for_work', AsyncMock(side_effect=[None, asyncio.CancelledError]))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(music_jobs._provider_loop('youtube'))
    assert schedule.await_count == 1


@pytest.mark.parametrize('status,delay', [('idle', None), ('migration_required', None), ('succeeded', 5)])
def test_avatar_idle_backs_off(monkeypatch, status, delay):
    monkeypatch.setattr(avatar_jobs, 'run_once', AsyncMock(return_value={'status': status}))
    wait = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(avatar_jobs, 'wait_for_work', wait)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(avatar_jobs.avatar_worker_loop())
    assert wait.call_args.kwargs['seconds'] == delay


@pytest.mark.parametrize('result,delay', [
    (CollectionResult(), None),
    (CollectionResult(accounts=1, deliveries_queued=1), 10),
    (CollectionResult(accounts=1, provider_wait_seconds=3600), 3600),
])
def test_x_idle_and_provider_backoff(monkeypatch, result, delay):
    monkeypatch.setattr(scheduler.settings, 'agent_run_on_start', True)
    monkeypatch.setattr(scheduler.settings, 'agent_interval_seconds', 86400)
    monkeypatch.setattr(scheduler, 'collect_x_once', AsyncMock(return_value=result))
    wait = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(scheduler, 'wait_for_work', wait)
    wake = asyncio.Event()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scheduler._x_loop(wake))
    assert wait.call_args.kwargs['seconds'] == delay
    assert wake.is_set() == bool(result.deliveries_queued)


def test_delivery_preserves_wakeup_received_during_send(monkeypatch):
    wake = asyncio.Event()
    async def deliver(*args):
        wake.set()
        return DeliveryResult()
    monkeypatch.setattr(scheduler, 'deliver_pending_once', deliver)
    wait = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(scheduler, 'wait_for_work', wait)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scheduler._delivery_loop(wake))
    assert wait.call_args.kwargs['seconds'] is None
    assert wait.call_args.kwargs['wake'].is_set()


def test_idle_health_is_ready_but_stale_or_failed_workers_are_not(monkeypatch):
    monkeypatch.setattr(worker_readiness.settings, 'runtime_cutover_enabled', True)
    monkeypatch.setattr(worker_readiness.settings, 'agent_enabled', True)
    state = {'state': 'idle', 'heartbeat_at': datetime.now(UTC).isoformat()}
    data = {'local_workers': {'music-youtube': state, 'music-spotify': state},
            'active_accounts': {}, 'registered_handlers': [], 'unimplemented_handlers': [], 'queue': {}}
    monkeypatch.setattr(worker_readiness, 'readiness', AsyncMock(return_value=data))
    assert asyncio.run(worker_readiness.inspect_readiness()).ready
    state['state'] = 'error'
    assert not asyncio.run(worker_readiness.inspect_readiness()).ready
    state.update(state='idle', heartbeat_at='2000-01-01T00:00:00+00:00')
    assert not asyncio.run(worker_readiness.inspect_readiness()).ready


def test_artist_lookup_is_scoped_and_cached_within_request(monkeypatch):
    from app.services.catalog_read import CatalogRead
    service = CatalogRead(None)
    service.repository = Mock()
    service.repository.artists.return_value = [{'id': 7}]
    assert service.artist(7)['id'] == 7
    assert service.artist(7)['id'] == 7
    service.repository.artists.assert_called_once_with(artist_id=7)
    service.repository.artists.return_value = []
    assert service.artist(8) is None
    assert service.artist(8) is None
    assert service.repository.artists.call_count == 2


@pytest.mark.parametrize('kind', ['music', 'avatar', 'x', 'delivery'])
def test_loop_errors_back_off_instead_of_hammering_database(monkeypatch, kind):
    module, function = {
        'music': (music_jobs, 'run_once'),
        'avatar': (avatar_jobs, 'run_once'),
        'x': (scheduler, 'collect_x_once'),
        'delivery': (scheduler, 'deliver_pending_once'),
    }[kind]
    monkeypatch.setattr(module, function, AsyncMock(side_effect=RuntimeError('offline')))
    wait = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(module, 'wait_for_work', wait)
    monkeypatch.setattr(scheduler.settings, 'agent_run_on_start', True)
    calls = {
        'music': lambda: music_jobs._provider_loop('spotify'),
        'avatar': avatar_jobs.avatar_worker_loop,
        'x': scheduler._x_loop,
        'delivery': scheduler._delivery_loop,
    }
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(calls[kind]())
    assert wait.call_args.kwargs['seconds'] is None
