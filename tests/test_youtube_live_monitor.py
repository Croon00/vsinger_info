"""Live-only monitor tests. No external calls or production database writes."""
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.youtube_catalog import Video, YouTubeClient, YouTubeFailure
from app.services import youtube_live_monitor as service

CHANNEL = 'UC' + 'a' * 22
NOW = datetime.now(UTC)


def account(id=1, *, discover=True, state=None):
    return dict(id=id, channel_id=CHANNEL, state=state or {}, playlist='uploads', pending=[], discover=discover)


def video(id='aaaaaaaaaaa', **updates):
    return Video(**dict(dict(id=id, channel_id=CHANNEL, title='Stream', availability='public', started_at=NOW), **updates))


def fake_db(monkeypatch, accounts):
    calls = []
    async def db(function, *args, **kwargs):
        calls.append((function.__name__, args, kwargs))
        return accounts if function is service.repository.claim else True
    monkeypatch.setattr(service, 'db_call', db)
    return calls


def test_discovery_is_separate_from_status_checks_and_only_keeps_current_public_streams(monkeypatch):
    calls = fake_db(monkeypatch, [account()])
    provider = AsyncMock()
    ids = ['aaaaaaaaaaa', 'bbbbbbbbbbb', 'ccccccccccc', 'ddddddddddd', 'eeeeeeeeeee']
    provider.discover_live_ids.return_value = ('uploads', ids)
    provider.videos.return_value = [video(), video(ids[1], started_at=None, scheduled=True, scheduled_at=NOW+timedelta(hours=2)),
                                  video(ids[2], ended_at=NOW), video(ids[3], availability='private'),
                                  video(ids[4], channel_id='UC'+'b'*22)]
    result = asyncio.run(service.run_once(provider))
    assert result == dict(accounts=1, live=1, scheduled=1, failed=0)
    saved = next(args for name, args, _ in calls if name == 'save')
    state, snapshot = saved[2:]
    assert state['candidate_ids'] == ids[:2]
    assert snapshot['streams'] == [dict(video_id=ids[0], title='Stream', started_at=NOW.isoformat())]
    assert snapshot['upcoming'] == [dict(video_id=ids[1], title='Stream', scheduled_at=(NOW+timedelta(hours=2)).isoformat())]
    checked = datetime.fromisoformat(snapshot['checked_at'])
    assert datetime.fromisoformat(state['next_discovery_at']) - checked == timedelta(minutes=10)
    assert datetime.fromisoformat(state['next_check_at']) - checked == timedelta(minutes=1)


def test_status_checks_batch_across_accounts_and_do_not_fetch_uploads(monkeypatch):
    accounts = [account(i, discover=False, state={'candidate_ids': ['aaaaaaaaaaa'], 'next_discovery_at': 'unchanged'}) for i in (1, 2)]
    calls = fake_db(monkeypatch, accounts)
    provider = AsyncMock()
    provider.videos.return_value = []  # Unavailable/ended candidates disappear, not replayed as live.
    asyncio.run(service.run_once(provider))
    provider.discover_live_ids.assert_not_called()
    provider.videos.assert_awaited_once_with(['aaaaaaaaaaa'])
    saved = [args for name, args, _ in calls if name == 'save']
    assert len(saved) == 2
    assert all(args[3]['streams'] == [] and args[2]['candidate_ids'] == [] for args in saved)
    assert all(args[2]['next_discovery_at'] == 'unchanged' for args in saved)


def test_discovery_skips_previously_checked_normal_uploads_but_keeps_pending(monkeypatch):
    calls = fake_db(monkeypatch, [account(state={'recent_ids': ['bbbbbbbbbbb'], 'candidate_ids': ['aaaaaaaaaaa']})])
    provider = AsyncMock()
    provider.discover_live_ids.return_value = ('uploads', ['bbbbbbbbbbb', 'ccccccccccc'])
    provider.videos.return_value = [video()]
    asyncio.run(service.run_once(provider))
    provider.videos.assert_awaited_once_with(['aaaaaaaaaaa', 'ccccccccccc'])
    assert any(name == 'save' for name, *_ in calls)


def test_quota_failure_defers_all_accounts_and_preserves_last_snapshot(monkeypatch):
    calls = fake_db(monkeypatch, [account()])
    provider = AsyncMock()
    provider.discover_live_ids.side_effect = YouTubeFailure('quotaExceeded', retry=True, retry_after=86400)
    result = asyncio.run(service.run_once(provider))
    assert result['failed'] == 1
    assert not any(name == 'save' for name, *_ in calls)
    assert next(kwargs for name, _, kwargs in calls if name == 'defer') == dict(seconds=86400, all_accounts=True)


def test_bad_channel_does_not_block_other_channels(monkeypatch):
    calls = fake_db(monkeypatch, [account(1), account(2)])
    provider = AsyncMock()
    provider.discover_live_ids.side_effect = [YouTubeFailure('channel_unavailable'), ('uploads', ['aaaaaaaaaaa'])]
    provider.videos.return_value = [video()]
    result = asyncio.run(service.run_once(provider))
    assert result['failed'] == 1 and result['live'] == 1
    assert next(args for name, args, _ in calls if name == 'save')[0]['id'] == 2


def test_status_failure_never_clears_previous_live_snapshot(monkeypatch):
    calls = fake_db(monkeypatch, [account(discover=False, state={'candidate_ids': ['aaaaaaaaaaa']})])
    provider = AsyncMock()
    provider.videos.side_effect = YouTubeFailure('transport', retry=True)
    asyncio.run(service.run_once(provider))
    assert not any(name == 'save' for name, *_ in calls)
    assert any(name == 'defer' for name, *_ in calls)


def test_discovery_only_reads_one_small_page_and_reuses_cached_playlist():
    paths = []
    def transport(request):
        paths.append(request.url.path)
        assert request.url.params['maxResults'] == '10'
        return httpx.Response(200, json={'items': [{'contentDetails': {'videoId': 'aaaaaaaaaaa'}}], 'nextPageToken': 'ignored'})
    provider = YouTubeClient('fixture', transport=httpx.MockTransport(transport), interval=0)
    assert asyncio.run(provider.discover_live_ids(CHANNEL, 'uploads')) == ('uploads', ['aaaaaaaaaaa'])
    assert paths == ['/youtube/v3/playlistItems']
