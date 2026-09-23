"""Music queue contracts using disposable PostgreSQL and fake providers only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from test_catalog_migration import database, local_server, row
from test_phase4_runtime import runtime_store
from app.services import music_jobs as service, notification_delivery
from app.repositories import worker_jobs as repo
from app.schemas.worker_jobs import JobRequest

CHANNEL = 'UC' + 'a' * 22
SPOTIFY = 's' * 22


@pytest.fixture
def store(runtime_store, monkeypatch):
    monkeypatch.setattr(service, 'catalog_runtime_session', notification_delivery.catalog_runtime_session)
    monkeypatch.setattr(service, 'HANDLERS', {})
    monkeypatch.setattr(service, 'WORKER_HEALTH', {})
    return runtime_store


def request(db, *, kind='youtube_collect', attempts=5):
    spotify = kind == 'spotify_collect'
    platform_id = SPOTIFY if spotify else CHANNEL
    account = row(db, 'external_accounts', platform='spotify' if spotify else 'youtube',
                  platform_id=platform_id, collection_enabled=True,
                  url=f'https://example.com/{platform_id}')
    db.commit()
    payload = {'spotify_artist_id': SPOTIFY} if spotify else {'channel_id': CHANNEL}
    if kind == 'youtube_collect':
        payload['youtube_video_id'] = 'abcdefghijk'
    return JobRequest(job_type=kind, external_account_id=account, payload=payload, max_attempts=attempts)


def persist(session, job, payload, value):
    session.execute(text('''INSERT INTO collection_states(external_account_id,cursor_value)
        VALUES (:id,:value) ON CONFLICT (external_account_id)
        DO UPDATE SET cursor_value=EXCLUDED.cursor_value'''), {'id': job.external_account_id, 'value': value})


def handler(collect=None, save=persist, timeout=1):
    return service.Handler(collect or AsyncMock(return_value='collected'), save, timeout_seconds=timeout)


def run(handlers, **kwargs):
    return asyncio.run(service.run_once(handlers=handlers, min_interval_seconds=0, **kwargs))


def test_enqueue_deduplicates_and_preserves_completed_job(store):
    req = request(store)
    first = asyncio.run(service.enqueue(req))
    assert asyncio.run(service.enqueue(req)) == first
    assert run({'youtube_collect': handler()})['status'] == 'succeeded'
    assert asyncio.run(service.enqueue(req)) == first
    assert run({'youtube_collect': handler()})['status'] == 'idle'
    assert store.execute('SELECT cursor_value FROM collection_states').fetchone()[0] == 'collected'
    assert asyncio.run(service.status(first))['attempt_count'] == 1


def test_explicit_new_request_run_creates_new_job(store):
    req = request(store)
    first = asyncio.run(service.enqueue(req))
    again = req.model_copy(update={'payload': {**req.payload, 'request_run': 'manual-2'}})
    assert asyncio.run(service.enqueue(again)) != first


@pytest.mark.parametrize('kind,payload', [
    ('youtube_collect', {'channel_id': CHANNEL, 'youtube_video_id': 'bad'}),
    ('youtube_poll', {'channel_id': CHANNEL, 'secret': 'not-allowed'}),
    ('spotify_collect', {'spotify_artist_id': SPOTIFY, 'version': 2}),
])
def test_invalid_payloads_are_rejected_before_enqueue(store, kind, payload):
    req = request(store, kind=kind).model_copy(update={'payload': payload})
    with pytest.raises(ValidationError):
        asyncio.run(service.enqueue(req))
    assert store.execute('SELECT count(*) FROM worker_jobs').fetchone()[0] == 0


@pytest.mark.parametrize('change', [
    "UPDATE external_accounts SET collection_enabled=false",
    "UPDATE external_accounts SET archived_at=clock_timestamp()",
    "UPDATE external_accounts SET platform_id='another'",
])
def test_spotify_requires_exact_registered_active_account(store, change):
    req = request(store, kind='spotify_collect')
    store.execute(change)
    store.commit()
    with pytest.raises(repo.JobConflict):
        asyncio.run(service.enqueue(req))


def test_missing_account_and_wrong_video_are_rejected(store):
    req = request(store)
    with pytest.raises(repo.JobConflict):
        asyncio.run(service.enqueue(req.model_copy(update={'external_account_id': 9999})))
    video = row(store, 'videos', platform='youtube', platform_video_id='xxxxxxxxxxx', title='fixture')
    store.commit()
    with pytest.raises(repo.JobConflict):
        asyncio.run(service.enqueue(req.model_copy(update={'video_id': video})))


def test_unimplemented_handler_never_claims_job(store):
    req = request(store)
    job_id = asyncio.run(service.enqueue(req))
    assert run({})['status'] == 'waiting_for_handler'
    assert run({'youtube_collect': handler()}, kinds=())['status'] == 'waiting_for_handler'
    assert asyncio.run(service.status(job_id))['attempt_count'] == 0


def test_unsupported_collectors_cannot_be_registered(store):
    with pytest.raises(ValueError):
        run({'lyrics_collect': handler()})
    with pytest.raises(ValidationError):
        JobRequest(job_type='karaoke_collect', external_account_id=1, payload={})


def test_retry_then_success_and_retry_after(store):
    job_id = asyncio.run(service.enqueue(request(store)))
    failure = handler(AsyncMock(side_effect=service.RetryableJobError(retry_after=1200)))
    assert run({'youtube_collect': failure})['status'] == 'retry'
    assert store.execute("SELECT next_attempt_at > clock_timestamp()+interval '1100 seconds' FROM worker_jobs").fetchone()[0]
    assert run({'youtube_collect': handler()})['status'] == 'idle'
    store.execute('UPDATE worker_jobs SET next_attempt_at=NULL')
    store.commit()
    assert run({'youtube_collect': handler()})['status'] == 'succeeded'
    assert asyncio.run(service.status(job_id))['attempt_count'] == 2


def test_failure_rolls_back_domain_write_and_never_logs_exception_text(store):
    job_id = asyncio.run(service.enqueue(request(store)))

    def broken(session, job, payload, value):
        persist(session, job, payload, value)
        raise ValueError('SECRET_PROVIDER_BODY')

    assert run({'youtube_collect': handler(save=broken)})['status'] == 'failed'
    assert store.execute('SELECT count(*) FROM collection_states').fetchone()[0] == 0
    assert asyncio.run(service.status(job_id))['last_error'] == 'ValueError'


def test_timeout_exhausts_attempt_budget(store):
    job_id = asyncio.run(service.enqueue(request(store, attempts=1)))

    async def blocked(*_):
        await asyncio.Event().wait()

    assert run({'youtube_collect': handler(blocked, timeout=0.02)})['status'] == 'failed'
    assert asyncio.run(service.status(job_id))['finished_at'] is not None


def test_expired_lease_recovered_and_old_owner_fenced(store):
    asyncio.run(service.enqueue(request(store)))
    with service.catalog_runtime_session() as session:
        old = repo.claim(session, ('youtube_collect',), owner='old', lease_seconds=10, min_interval_seconds=0)
    store.execute("UPDATE worker_jobs SET lease_expires_at=clock_timestamp()-interval '1 second'")
    store.commit()
    assert run({'youtube_collect': handler()})['status'] == 'succeeded'
    with service.catalog_runtime_session() as session:
        assert not repo.fail(session, old, error='stale', retry=True)
        assert not repo.renew(session, old, lease_seconds=10)
    assert store.execute('SELECT attempt_count FROM worker_jobs').fetchone()[0] == 2


def test_disabled_account_cancelled_before_provider_call(store):
    job_id = asyncio.run(service.enqueue(request(store)))
    store.execute('UPDATE external_accounts SET collection_enabled=false')
    store.commit()
    collect = AsyncMock()
    run({'youtube_collect': handler(collect)})
    collect.assert_not_awaited()
    assert asyncio.run(service.status(job_id))['status'] == 'cancelled'


def test_malformed_stored_legacy_payload_fails_without_provider(store):
    job_id = asyncio.run(service.enqueue(request(store)))
    store.execute("UPDATE worker_jobs SET payload='{}'::jsonb")
    store.commit()
    collect = AsyncMock()
    assert run({'youtube_collect': handler(collect)})['status'] == 'failed'
    collect.assert_not_awaited()
    assert asyncio.run(service.status(job_id))['last_error'] == 'ValidationError'


def test_cancel_running_job_interrupts_collect_and_blocks_persist(store):
    job_id = asyncio.run(service.enqueue(request(store)))
    save = []

    async def scenario():
        entered = asyncio.Event()

        async def blocked(*_):
            entered.set()
            await asyncio.Event().wait()

        worker = asyncio.create_task(service.run_once(
            handlers={'youtube_collect': handler(blocked, save=lambda *_: save.append(1))},
            lease_seconds=0.3, min_interval_seconds=0))
        await entered.wait()
        assert await service.cancel(job_id)
        assert (await asyncio.wait_for(worker, 2))['status'] == 'lease_lost'

    asyncio.run(scenario())
    assert save == []
    assert asyncio.run(service.status(job_id))['status'] == 'cancelled'


def test_shutdown_releases_for_resume(store):
    job_id = asyncio.run(service.enqueue(request(store)))

    async def scenario():
        entered = asyncio.Event()

        async def blocked(*_):
            entered.set()
            await asyncio.Event().wait()

        worker = asyncio.create_task(service.run_once(handlers={'youtube_collect': handler(blocked)}))
        await entered.wait()
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    asyncio.run(scenario())
    assert asyncio.run(service.status(job_id))['status'] == 'retry'
    assert run({'youtube_collect': handler()})['status'] == 'succeeded'


def test_heartbeat_keeps_long_job_alive_and_limits_provider_concurrency(store):
    req = request(store)
    asyncio.run(service.enqueue(req))
    asyncio.run(service.enqueue(req.model_copy(update={'payload': {**req.payload,'request_run':'two'}})))

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def collect(*_):
            entered.set()
            await release.wait()
            return 'collected'

        first = asyncio.create_task(service.run_once(handlers={'youtube_collect': handler(collect, timeout=3)},
                                                      lease_seconds=0.6, min_interval_seconds=0))
        await entered.wait()
        await asyncio.sleep(0.8)
        assert (await service.run_once(handlers={'youtube_collect': handler()}, min_interval_seconds=0))['status'] == 'idle'
        release.set()
        assert (await first)['status'] == 'succeeded'

    asyncio.run(scenario())
    assert run({'youtube_collect': handler()})['status'] == 'succeeded'


def test_due_youtube_poll_scheduling_is_idempotent(store):
    request(store, kind='youtube_poll')
    with service.catalog_runtime_session() as session:
        assert repo.schedule_youtube_polls(session) == 1
    with service.catalog_runtime_session() as session:
        assert repo.schedule_youtube_polls(session) == 0
    assert store.execute('SELECT count(*) FROM worker_jobs').fetchone()[0] == 1
    assert run({'youtube_poll': handler()})['status'] == 'succeeded'


def test_readiness_has_identity_and_queue_but_never_claims(store):
    job_id = asyncio.run(service.enqueue(request(store)))
    status = asyncio.run(service.readiness())
    assert status['database_verified'] and status['queue']['due'] == 1
    assert set(status['unimplemented_handlers']) == {'youtube_poll','youtube_collect','spotify_collect'}
    assert asyncio.run(service.status(job_id))['attempt_count'] == 0


def test_cli_blocks_mutation_before_cutover(monkeypatch):
    from scripts.music_jobs import execute
    monkeypatch.setattr(service.settings, 'runtime_cutover_enabled', False)
    with pytest.raises(RuntimeError):
        asyncio.run(execute(SimpleNamespace(command='cancel', id=1)))


def test_ready_endpoint_is_read_only_and_does_not_expose_instance(store, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app
    monkeypatch.setattr(service.settings, 'runtime_cutover_enabled', False)
    job_id = asyncio.run(service.enqueue(request(store)))
    with TestClient(app) as client:
        response = client.get('/ready')
    assert response.status_code == 200
    assert response.json()['database_verified']
    assert 'instance_id' not in response.json()
    assert asyncio.run(service.status(job_id))['attempt_count'] == 0


def test_unimplemented_handlers_are_not_reported_operationally_ready(store, monkeypatch):
    from app.services.worker_readiness import inspect_readiness
    monkeypatch.setattr(service.settings, 'runtime_cutover_enabled', True)
    monkeypatch.setattr(service.settings, 'agent_enabled', True)
    assert not asyncio.run(inspect_readiness()).ready


def test_readiness_requires_provider_credentials_only_for_registered_active_accounts(store, monkeypatch):
    from app.services.worker_readiness import inspect_readiness
    request(store)
    monkeypatch.setattr(service.settings, 'youtube_api_key', None)
    monkeypatch.setattr(service.settings, 'spotify_client_id', None)
    monkeypatch.setattr(service.settings, 'spotify_client_secret', None)
    first = asyncio.run(inspect_readiness())
    assert first.active_accounts == {'youtube': 1}
    assert first.missing_credentials == ['YOUTUBE_API_KEY']
    row(store, 'external_accounts', platform='spotify', platform_id=SPOTIFY,
        collection_enabled=True, url='https://example.com/spotify')
    store.commit()
    second = asyncio.run(inspect_readiness())
    assert second.active_accounts == {'youtube': 1, 'spotify': 1}
    assert set(second.missing_credentials) == {'YOUTUBE_API_KEY', 'SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET'}


def test_account_identity_change_during_collection_rolls_back_result(store):
    job_id = asyncio.run(service.enqueue(request(store)))

    async def collect(*_):
        store.execute("UPDATE external_accounts SET platform_id='UCbbbbbbbbbbbbbbbbbbbbbb'")
        store.commit()
        return 'collected'

    assert run({'youtube_collect': handler(collect)})['status'] == 'failed'
    assert store.execute('SELECT count(*) FROM collection_states').fetchone()[0] == 0
    assert asyncio.run(service.status(job_id))['last_error'] == 'JobConflict'


def test_spotify_runs_while_youtube_is_waiting(store):
    asyncio.run(service.enqueue(request(store)))
    asyncio.run(service.enqueue(request(store, kind='spotify_collect')))

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def youtube(*_):
            entered.set()
            await release.wait()
            return 'youtube'

        first = asyncio.create_task(service.run_once(handlers={'youtube_collect': handler(youtube, timeout=3)},
                                                      min_interval_seconds=0))
        await entered.wait()
        try:
            second = await service.run_once(handlers={'spotify_collect': handler()}, min_interval_seconds=0)
            assert second['status'] == 'succeeded'
        finally:
            release.set()
            await first

    asyncio.run(scenario())


def test_transient_database_failure_is_retryable(store):
    from sqlalchemy.exc import OperationalError
    job_id = asyncio.run(service.enqueue(request(store)))

    def broken(*_):
        raise OperationalError('sql', {}, RuntimeError('connection reset'))

    assert run({'youtube_collect': handler(save=broken)})['status'] == 'retry'
    assert asyncio.run(service.status(job_id))['last_error'] == 'OperationalError'


def test_provider_job_cooldown_is_enforced(store):
    req = request(store)
    asyncio.run(service.enqueue(req))
    asyncio.run(service.enqueue(req.model_copy(update={'payload': {**req.payload, 'request_run': 'second'}})))
    assert run({'youtube_collect': handler()})['status'] == 'succeeded'
    assert asyncio.run(service.run_once(handlers={'youtube_collect': handler()}, min_interval_seconds=60))['status'] == 'idle'


def test_music_worker_respects_cutover_flags_without_db(monkeypatch):
    monkeypatch.setattr(service.settings, 'runtime_cutover_enabled', False)
    call = AsyncMock(side_effect=AssertionError('must not touch DB'))
    monkeypatch.setattr(service, 'db_call', call)
    asyncio.run(service.music_worker_loop())
    call.assert_not_awaited()


def test_ready_returns_503_without_leaking_database_errors(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app
    from app.services import worker_readiness
    monkeypatch.setattr(worker_readiness, 'readiness', AsyncMock(side_effect=RuntimeError('SECRET_DB_URL')))
    with TestClient(app) as client:
        response = client.get('/ready')
    assert response.status_code == 503
    assert not response.json()['database_verified']
    assert 'SECRET' not in response.text
