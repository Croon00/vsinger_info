"""Holodex fixtures only: no real provider calls or production database writes."""
import asyncio
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

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


def fake_db(monkeypatch, accounts=None):
    calls = []
    async def db(function, *args, **kwargs):
        calls.append((function.__name__, args, kwargs))
        if function is service.repository.claim_holodex:
            return accounts if accounts is not None else [dict(id=1, channel_id=CHANNEL), dict(id=2, channel_id=OTHER)]
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
    assert datetime.fromisoformat(updates[0]['state']['next_check_at']) - datetime.fromisoformat(snapshot['checked_at']) == timedelta(hours=1)
    assert datetime.fromisoformat(updates[0]['state']['next_live_check_at']) - datetime.fromisoformat(snapshot['live_checked_at']) == timedelta(minutes=3)


def test_three_minute_check_promotes_due_upcoming_and_preserves_discovery(monkeypatch):
    checked = (NOW-timedelta(minutes=30)).isoformat()
    discovery_due = (NOW+timedelta(minutes=30)).isoformat()
    upcoming = [dict(video_id='eeeeeeeeeee', title='Scheduled', scheduled_at=NOW.isoformat()),
        dict(video_id='fffffffffff', title='Future', scheduled_at=(NOW+timedelta(hours=2)).isoformat()),
        dict(video_id='ggggggggggg', title='Unknown', scheduled_at=None)]
    accounts = [dict(id=1, channel_id=CHANNEL, discover=False,
        state={'next_check_at': discovery_due, 'lease_token': 'old-token'},
        snapshot=dict(provider='holodex', checked_at=checked, upcoming=upcoming,
            streams=[dict(video_id='aaaaaaaaaaa'), dict(video_id='bbbbbbbbbbb')])),
        dict(id=2, channel_id=OTHER, discover=False, state={'next_check_at': discovery_due},
        snapshot=dict(provider='holodex', checked_at=checked, upcoming=[], streams=[dict(video_id='ccccccccccc')]))]
    calls = fake_db(monkeypatch, accounts)
    provider = AsyncMock()
    provider.live.return_value = [HolodexStream.model_validate(stream()),
        HolodexStream.model_validate(stream(id='ddddddddddd')),
        HolodexStream.model_validate(stream(id='fffffffffff')),
        HolodexStream.model_validate(stream(id='eeeeeeeeeee', status='live'))]
    result = asyncio.run(service.run_holodex_once(provider))
    provider.live.assert_awaited_once_with([CHANNEL, OTHER])
    assert result == dict(accounts=2, live=2, scheduled=2, failed=0)
    updates = next(args[1] for name, args, _ in calls if name == 'save_holodex_batch')
    assert [v['video_id'] for v in updates[0]['snapshot']['streams']] == ['aaaaaaaaaaa', 'eeeeeeeeeee']
    assert updates[0]['snapshot']['upcoming'] == upcoming[1:]
    assert updates[1]['snapshot']['streams'] == []
    assert all(u['snapshot']['checked_at'] == checked and u['state']['next_check_at'] == discovery_due for u in updates)
    assert all('lease_token' not in u['state'] for u in updates)


@pytest.mark.parametrize('response', ['waiting', 'rescheduled', 'missing'])
def test_due_upcoming_status_refresh_handles_delay_reschedule_and_removal(monkeypatch, response):
    checked = (NOW-timedelta(minutes=30)).isoformat()
    upcoming = [dict(video_id='aaaaaaaaaaa', title='Waiting', scheduled_at=NOW.isoformat())]
    accounts = [dict(id=1, channel_id=CHANNEL, discover=False, state={},
        snapshot=dict(provider='holodex', checked_at=checked, upcoming=upcoming, streams=[]))]
    calls = fake_db(monkeypatch, accounts)
    provider = AsyncMock()
    scheduled = NOW+timedelta(hours=1) if response == 'rescheduled' else NOW
    provider.live.return_value = [] if response == 'missing' else [HolodexStream.model_validate(
        stream(status='upcoming', start_actual=None, start_scheduled=scheduled.isoformat()))]
    result = asyncio.run(service.run_holodex_once(provider))
    snapshot = next(args[1][0]['snapshot'] for name, args, _ in calls if name == 'save_holodex_batch')
    assert result['live'] == 0
    assert snapshot['checked_at'] == checked
    assert snapshot['streams'] == []
    if response == 'missing':
        assert snapshot['upcoming'] == []
    else:
        assert len(snapshot['upcoming']) == 1
        assert snapshot['upcoming'][0]['scheduled_at'] == scheduled.isoformat()


def test_no_due_accounts_makes_no_holodex_requests(monkeypatch):
    fake_db(monkeypatch, [])
    provider = AsyncMock()
    assert asyncio.run(service.run_holodex_once(provider))['accounts'] == 0
    provider.live.assert_not_called()


@pytest.mark.parametrize('retry_after,expected', [(60, 180), (900, 900)])
def test_live_only_failure_preserves_snapshot_and_obeys_provider_delay(monkeypatch, retry_after, expected):
    calls = fake_db(monkeypatch, [dict(id=1, channel_id=CHANNEL, discover=False)])
    provider = AsyncMock()
    provider.live.side_effect = HolodexFailure('rate_limited', retry_after=retry_after)
    assert asyncio.run(service.run_holodex_once(provider))['failed'] == 1
    assert not any(name == 'save_holodex_batch' for name, _, _ in calls)
    assert next(kwargs for name, _, kwargs in calls if name == 'defer') == dict(
        seconds=expected, all_accounts=True, namespace='holodex_live_monitor')


@pytest.mark.parametrize('retry_after,expected', [(300, 3600), (7200, 7200)])
def test_failure_preserves_snapshot_and_defers_only_holodex(monkeypatch, retry_after, expected):
    calls = fake_db(monkeypatch)
    provider = AsyncMock()
    provider.live.side_effect = HolodexFailure('rate_limited', retry_after=retry_after)
    result = asyncio.run(service.run_holodex_once(provider))
    assert result['failed'] == 2
    assert not any(name == 'save_holodex_batch' for name, _, _ in calls)
    assert next(kwargs for name, _, kwargs in calls if name == 'defer') == dict(
        seconds=expected, all_accounts=True, namespace='holodex_live_monitor')


def test_monitor_selects_holodex_even_without_youtube_key(monkeypatch):
    monkeypatch.setattr(service.settings, 'holodex_api_key', 'fixture')
    monkeypatch.setattr(service.settings, 'youtube_api_key', None)
    holodex = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(service, 'run_holodex_once', holodex)
    monkeypatch.setattr(service, 'run_once', lambda: pytest.fail('YouTube monitor must not run'))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.monitor_loop())
    holodex.assert_awaited_once()


def test_unexpected_failure_also_waits_an_hour_before_retry(monkeypatch):
    calls = fake_db(monkeypatch)
    provider = AsyncMock()
    provider.live.side_effect = RuntimeError('fixture failure')
    with pytest.raises(RuntimeError):
        asyncio.run(service.run_holodex_once(provider))
    assert next(kwargs for name, _, kwargs in calls if name == 'defer') == dict(
        seconds=3600, namespace='holodex_live_monitor')
    assert not any(name == 'save_holodex_batch' for name, _, _ in calls)


def test_key_is_server_only_and_hidden_in_settings_repr():
    settings = Settings(_env_file=None, holodex_api_key='fixture-secret')
    assert settings.holodex_api_key == 'fixture-secret'
    assert 'fixture-secret' not in repr(settings)
    assert Settings(_env_file=None, holodex_api_key='').holodex_api_key is None
    assert Settings(_env_file=None).holodex_poll_seconds == 3600
    assert Settings(_env_file=None).holodex_live_check_seconds == 180


def test_claim_accepts_valid_channel_ids_after_sql_interpolation():
    from app.repositories import youtube_live_monitor as repository
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    assert repository.claim_holodex(session, 'fixture') == []
    sql = str(session.execute.call_args.args[0])
    pattern = re.search(r"platform_id ~ '([^']+)'", sql).group(1)
    assert re.fullmatch(pattern, CHANNEL)
    assert not re.fullmatch(pattern, 'UCshort')
    assert not re.fullmatch(pattern, CHANNEL+'extra')


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
            # An old one-minute next_check_at must not trigger an early request
            # after switching to hourly polling.
            session.execute(text("""UPDATE collection_states SET provider_state=
                jsonb_set(jsonb_set(provider_state,'{holodex_live_monitor}',CAST(:state AS jsonb)),
                          '{youtube_live_snapshot,checked_at}',to_jsonb(CAST(:checked AS text)))
                WHERE external_account_id=:id"""), dict(id=ids[0],
                    state=json.dumps({'next_check_at': (NOW-timedelta(minutes=1)).isoformat()}),
                    checked=(NOW-timedelta(minutes=10)).isoformat()))
            assert repository.claim_holodex(session, 'hourly', poll_seconds=3600) == []
            # Only known live or scheduled-at/past upcoming entries qualify
            # between full discoveries. Unknown/future schedules must wait.
            for scheduled, expected in [(None, False),
                    ((NOW+timedelta(minutes=5)).isoformat(), False),
                    ((NOW-timedelta(seconds=1)).isoformat(), True)]:
                snapshot = dict(provider='holodex', checked_at=(NOW-timedelta(minutes=10)).isoformat(),
                    live_checked_at=(NOW-timedelta(minutes=5)).isoformat(), streams=[],
                    upcoming=[dict(video_id='aaaaaaaaaaa', title='Waiting', scheduled_at=scheduled)])
                session.execute(text("UPDATE collection_states SET provider_state=jsonb_set(provider_state,'{youtube_live_snapshot}',CAST(:snapshot AS jsonb)) WHERE external_account_id=:id"),
                    dict(id=ids[0], snapshot=json.dumps(snapshot)))
                session.flush()
                with session.begin_nested() as savepoint:
                    due = repository.claim_holodex(session, 'scheduled', poll_seconds=3600, live_check_seconds=180)
                    assert bool(due) is expected
                    if expected:
                        assert due[0]['discover'] is False
                    savepoint.rollback()
            snapshot = dict(provider='holodex', checked_at=(NOW-timedelta(minutes=10)).isoformat(),
                live_checked_at=(NOW-timedelta(minutes=5)).isoformat(), upcoming=[],
                streams=[dict(video_id='aaaaaaaaaaa', title='Live', started_at=NOW.isoformat())])
            session.execute(text("UPDATE collection_states SET provider_state=jsonb_set(provider_state,'{youtube_live_snapshot}',CAST(:snapshot AS jsonb)) WHERE external_account_id=:id"),
                dict(id=ids[0], snapshot=json.dumps(snapshot)))
            due = repository.claim_holodex(session, 'three-minutes', poll_seconds=3600, live_check_seconds=180)
            assert [a['id'] for a in due] == [ids[0]] and due[0]['discover'] is False
            assert due[0]['snapshot'] == snapshot
    finally:
        engine.dispose()
