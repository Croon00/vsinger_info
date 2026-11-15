"""Holodex fixtures only: no real provider calls or production database writes."""
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.integrations.holodex import HolodexClient, HolodexFailure, HolodexStream
from app.services import youtube_live_monitor as service
from test_catalog_migration import database, local_server, apply, row

CHANNEL = 'UC' + 'a'*22
OTHER = 'UC' + 'b'*22
NOW = datetime.now(UTC)


def stream(**changes):
    return dict(dict(id='aaaaaaaaaaa', channel_id=CHANNEL, type='stream', title='Live',
                     status='live', start_actual=NOW.isoformat()), **changes)


def client(body, *, status=200, headers=None):
    def respond(request):
        assert request.headers['X-APIKEY'] == 'fixture-secret'
        assert 'fixture-secret' not in str(request.url)
        return httpx.Response(status, json=body, headers=headers)
    return HolodexClient('fixture-secret', transport=httpx.MockTransport(respond))


def test_normalizes_live_upcoming_and_only_requested_channels():
    rows = [stream(), stream(id='bbbbbbbbbbb', status='upcoming', start_actual=None,
                start_scheduled='2026-11-16T01:00:00+09:00'),
            stream(id='ccccccccccc', channel_id=OTHER), stream(status='past'),
            stream(end_actual=NOW.isoformat()), stream(type='placeholder'),
            {**stream(id='ddddddddddd'), 'channel_id': None, 'channel': {'id': CHANNEL}}]
    found = asyncio.run(client(rows).live([CHANNEL]))
    assert [v.id for v in found] == ['aaaaaaaaaaa', 'bbbbbbbbbbb', 'ddddddddddd']
    assert found[1].start_actual is None and found[1].start_scheduled.utcoffset() == timedelta(hours=9)


def test_batches_channels_without_duplicates_and_does_not_truncate_videos():
    channels = ['UC'+str(i).zfill(22) for i in range(51)]
    calls = []
    def respond(request):
        batch = request.url.params['channels'].split(',')
        assert len(batch) <= 50
        calls.append(batch)
        return httpx.Response(200, json=[stream(id=str(i).zfill(11), channel_id=batch[0]) for i in range(80)])
    found = asyncio.run(HolodexClient('fixture', transport=httpx.MockTransport(respond)).live(channels+[channels[0]]))
    assert len(calls) == 2 and set(sum(calls, [])) == set(channels)
    assert len(found) == 80


@pytest.mark.parametrize('status,reason,delay', [(401, 'unauthorized', 900), (403, 'unauthorized', 900),
    (429, 'rate_limited', 120), (500, 'provider_error', 120)])
def test_sanitizes_provider_errors_and_honors_retry_after(status, reason, delay):
    with pytest.raises(HolodexFailure) as error:
        asyncio.run(client({'error': 'fixture-secret'}, status=status, headers={'Retry-After': '120'}).live([CHANNEL]))
    assert error.value.reason == reason and error.value.retry_after == delay
    assert 'fixture-secret' not in str(error.value)


@pytest.mark.parametrize('body', [{}, [None], [stream(id='bad')], [stream(start_actual='invalid')],
    [stream(start_actual='2026-11-15T01:00:00')]])
def test_malformed_responses_fail_instead_of_clearing_snapshot(body):
    with pytest.raises(HolodexFailure, match='malformed_response'):
        asyncio.run(client(body).live([CHANNEL]))


def test_transport_failure_is_sanitized():
    def fail(request):
        raise httpx.ReadTimeout('fixture-secret')
    with pytest.raises(HolodexFailure, match='transport'):
        asyncio.run(HolodexClient('fixture', transport=httpx.MockTransport(fail)).live([CHANNEL]))


def fake_db(monkeypatch):
    calls = []
    async def db(function, *args, **kwargs):
        calls.append((function.__name__, args, kwargs))
        if function is service.repository.claim_holodex:
            return [dict(id=1, channel_id=CHANNEL), dict(id=2, channel_id=OTHER)]
        if function is service.repository.save_holodex_batch:
            return {1, 2}
    monkeypatch.setattr(service, 'db_call', db)
    return calls


def test_saves_holodex_snapshot_without_any_youtube_request(monkeypatch):
    calls = fake_db(monkeypatch)
    monkeypatch.setattr(service, 'YouTubeClient', lambda *_: pytest.fail('YouTube API must not be used'))
    provider = AsyncMock()
    provider.live.return_value = [HolodexStream.model_validate(stream()),
        HolodexStream.model_validate(stream(id='bbbbbbbbbbb', status='upcoming', start_actual=None))]
    result = asyncio.run(service.run_holodex_once(provider))
    assert result == dict(accounts=2, live=1, scheduled=1, failed=0)
    updates = next(args[1] for name, args, _ in calls if name == 'save_holodex_batch')
    assert updates[0]['snapshot']['provider'] == 'holodex'
    assert updates[0]['snapshot']['upcoming'][0]['scheduled_at'] is None
    assert updates[1]['snapshot']['streams'] == updates[1]['snapshot']['upcoming'] == []
    snapshot = updates[0]['snapshot']
    assert datetime.fromisoformat(updates[0]['state']['next_check_at']) - datetime.fromisoformat(snapshot['checked_at']) == timedelta(seconds=60)


def test_failure_preserves_snapshot_and_defers_only_holodex(monkeypatch):
    calls = fake_db(monkeypatch)
    provider = AsyncMock()
    provider.live.side_effect = HolodexFailure('rate_limited', retry_after=300)
    result = asyncio.run(service.run_holodex_once(provider))
    assert result['failed'] == 2
    assert not any(name == 'save_holodex_batch' for name, _, _ in calls)
    assert next(kwargs for name, _, kwargs in calls if name == 'defer') == dict(
        seconds=300, all_accounts=True, namespace='holodex_live_monitor')


def test_monitor_selects_holodex_even_without_youtube_key(monkeypatch):
    monkeypatch.setattr(service.settings, 'holodex_api_key', 'fixture')
    monkeypatch.setattr(service.settings, 'youtube_api_key', None)
    holodex = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(service, 'run_holodex_once', holodex)
    monkeypatch.setattr(service, 'run_once', lambda: pytest.fail('YouTube monitor must not run'))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.monitor_loop())
    holodex.assert_awaited_once()


def test_key_is_server_only_and_hidden_in_settings_repr():
    settings = Settings(_env_file=None, holodex_api_key='fixture-secret')
    assert settings.holodex_api_key == 'fixture-secret'
    assert 'fixture-secret' not in repr(settings)
    assert Settings(_env_file=None, holodex_api_key='').holodex_api_key is None


def test_holodex_leases_ignore_youtube_quota_and_recheck_account_on_save(database):
    import json
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.repositories import youtube_live_monitor as repository
    apply(database)
    artist = row(database, 'artists', slug='holodex-test', entity_kind='solo', name_native='Singer', show_in_catalog=True)
    ids = []
    for channel in (CHANNEL, OTHER, 'UC'+'c'*22):
        account = row(database, 'external_accounts', platform='youtube', platform_id=channel,
                      url='https://youtube.com/channel/'+channel, collection_enabled=True)
        row(database, 'artist_external_accounts', artist_id=artist, account_id=account, relationship='owner')
        state = {'youtube_live_monitor': {'retry_at': (NOW+timedelta(days=1)).isoformat()}}
        database.execute('INSERT INTO collection_states(external_account_id,provider_state) VALUES (%s,%s::jsonb)',
                         (account, json.dumps(state)))
        ids.append(account)
    database.commit()
    info = database.info
    engine = create_engine(f'postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}')
    try:
        with Session(engine) as session:
            accounts = repository.claim_holodex(session, 'first')
            session.commit()
            assert {a['id'] for a in accounts} == set(ids)
            assert repository.claim_holodex(session, 'second') == []
            session.execute(text('UPDATE external_accounts SET collection_enabled=false WHERE id=:id'), {'id': ids[1]})
            session.execute(text("UPDATE collection_states SET provider_state=jsonb_set(provider_state,'{holodex_live_monitor,lease_until}',to_jsonb((clock_timestamp()-interval '1 second')::text)) WHERE external_account_id=:id"), {'id': ids[2]})
            updates = [dict(id=a['id'], channel_id=a['channel_id'], state={'next_check_at': (NOW+timedelta(minutes=1)).isoformat()},
                snapshot={'provider': 'holodex', 'checked_at': NOW.isoformat(), 'streams': [], 'upcoming': []}) for a in accounts]
            assert repository.save_holodex_batch(session, 'wrong-token', updates) == set()
            assert repository.save_holodex_batch(session, 'first', updates) == {ids[0]}
            repository.defer(session, 'first', namespace='holodex_live_monitor', all_accounts=True, seconds=300)
            state = session.execute(text('SELECT provider_state FROM collection_states WHERE external_account_id=:id'), {'id': ids[0]}).scalar_one()
            assert state['youtube_live_monitor']['retry_at']
            assert state['youtube_live_snapshot']['provider'] == 'holodex'
            assert state['holodex_live_monitor']['retry_at']
    finally:
        engine.dispose()
