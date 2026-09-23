"""Stage 3: disposable PostgreSQL, fake YouTube/LLM; no production I/O."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_catalog_migration import database, local_server, row
from test_phase4_runtime import runtime_store
from test_music_jobs import store, request, CHANNEL
from app.core.config import settings
from app.db.catalog_session import get_catalog_session
from app.api.routers.read_api import router
from app.integrations.youtube_catalog import Video, Comment, YouTubeClient, YouTubeFailure, parse_setlist, purpose
from app.services import music_jobs, youtube_collection as service


def video(**updates):
    now = datetime.now(UTC)
    return Video(**dict(dict(id='abcdefghijk', channel_id=CHANNEL, title='歌枠 Singing', description='original description',
                            published_at=now-timedelta(days=3), started_at=now-timedelta(days=3),
                            ended_at=now-timedelta(days=2), duration_seconds=7200, availability='public'), **updates))


def comment(content='00:30 Song One / Original\n02:10 Song Two — Singer A & Singer B'):
    return Comment(id='comment-id', text=content, captured_at=datetime.now(UTC))


@pytest.fixture
def provider(monkeypatch):
    fake = SimpleNamespace(videos=AsyncMock(return_value=[video()]), comments=AsyncMock(return_value=([comment()], False)),
                           recent=AsyncMock(return_value=('uploads', [video()], False)))
    monkeypatch.setattr(service, 'client', lambda: fake)
    monkeypatch.setattr(service, 'extract_youtube_setlist', AsyncMock(return_value=None))
    return fake


def run():
    return asyncio.run(music_jobs.run_once(handlers=service.handlers(), min_interval_seconds=0))


def queue(db, **payload):
    req = request(db)
    req = req.model_copy(update={'payload': {**req.payload, **payload}})
    return req, asyncio.run(music_jobs.enqueue(req))


def test_archive_to_real_api_preserves_raw_source_and_unresolved_attribution(store, provider, monkeypatch):
    req, _ = queue(store)
    artist = row(store, 'artists', entity_kind='group', slug='group', name_native='Group', show_in_catalog=True)
    row(store, 'artist_external_accounts', artist_id=artist, account_id=req.external_account_id, relationship='owner')
    store.commit()
    assert run()['status'] == 'succeeded'
    archive = store.execute('SELECT id,setlist_state,broadcast_at FROM live_archives').fetchone()
    assert archive[1] == 'partial'
    assert archive[2] == provider.videos.return_value[0].started_at
    assert store.execute('SELECT count(*) FROM performances WHERE song_id IS NULL').fetchone()[0] == 2
    assert store.execute('SELECT count(*) FROM performance_artists').fetchone()[0] == 0
    source = store.execute('SELECT external_id,content_text,source_metadata FROM source_documents').fetchone()
    assert source[0] == 'comment-id' and source[1] == comment().text
    assert source[2]['extractor'] == 'rules-1' and source[2]['attribution'] == 'unresolved'
    app = FastAPI()
    app.include_router(router, prefix='/api')
    def session():
        with music_jobs.catalog_runtime_session() as current:
            yield current
    app.dependency_overrides[get_catalog_session] = session
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app) as api:
        api.headers['X-API-Key'] = 'fixture'
        lives = api.get(f'/api/artists/{artist}/lives')
        assert lives.status_code == 200, lives.text
        assert lives.json()['total'] == 1
        detail = api.get(f'/api/lives/{archive[0]}')
        assert detail.status_code == 200, detail.text
        assert len(detail.json()['performances']) == 2
        found = api.get('/api/search?q=Song%20One')
        assert found.status_code == 200, found.text
        assert found.json()['total'] == 1
    # No GET caused another provider request.
    assert provider.videos.await_count == 1


def test_delayed_comment_is_durable_separate_from_network_retry_budget(store, provider):
    _, job = queue(store)
    provider.comments.return_value = ([], False)
    assert run()['status'] == 'succeeded'
    waiting = store.execute("SELECT id,payload,attempt_count,next_attempt_at FROM worker_jobs WHERE status='pending'").fetchone()
    assert waiting[1]['wait_count'] == 1 and waiting[2] == 0 and waiting[3] > datetime.now(UTC)
    assert store.execute('SELECT count(*) FROM live_archives').fetchone()[0] == 0
    assert run()['status'] == 'idle'
    store.execute("UPDATE worker_jobs SET next_attempt_at=NULL WHERE status='pending'")
    store.commit()
    provider.comments.return_value = ([comment()], False)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM videos').fetchone()[0] == 1
    assert store.execute('SELECT count(*) FROM performances').fetchone()[0] == 2
    assert asyncio.run(music_jobs.status(job))['attempt_count'] == 1


@pytest.mark.parametrize('reason,outcome', [('commentsDisabled', 'comments_disabled'), ('videoNotFound', 'private_or_deleted')])
def test_terminal_comment_failure_not_retried(store, provider, reason, outcome):
    queue(store)
    provider.comments.side_effect = YouTubeFailure(reason)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT setlist_state FROM live_archives').fetchone()[0] == 'unavailable'
    assert store.execute("SELECT source_metadata->>'outcome' FROM source_documents").fetchone()[0] == outcome
    assert run()['status'] == 'idle'


def test_wait_limit_and_video_unavailable_are_explicit(store, provider):
    queue(store, wait_count=168)
    provider.comments.return_value = ([], False)
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT source_metadata->>'outcome' FROM source_documents").fetchone()[0] == 'wait_exhausted'
    assert store.execute('SELECT count(*) FROM worker_jobs').fetchone()[0] == 1


def test_private_or_deleted_video_does_not_invent_metadata(store, provider):
    queue(store)
    provider.videos.return_value = []
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM videos').fetchone()[0] == 0
    assert store.execute("SELECT source_metadata->>'outcome' FROM source_documents").fetchone()[0] == 'private_or_deleted'


def test_provider_retry_after_and_no_partial_write(store, provider):
    _, job = queue(store)
    provider.comments.side_effect = YouTubeFailure('quotaExceeded', retry=True, retry_after=86400)
    assert run()['status'] == 'retry'
    assert store.execute('SELECT count(*) FROM videos').fetchone()[0] == 0
    assert asyncio.run(music_jobs.status(job))['next_attempt_at'] > datetime.now(UTC)+timedelta(hours=23)


def test_reprocessing_and_manual_changes_are_never_replaced(store, provider):
    req, _ = queue(store)
    assert run()['status'] == 'succeeded'
    perf = store.execute('SELECT id FROM performances ORDER BY ordinal').fetchone()[0]
    guest = row(store, 'artists', entity_kind='solo', slug='guest', name_native='Guest')
    row(store, 'performance_artists', performance_id=perf, artist_id=guest, role='guest')
    store.execute("UPDATE performances SET raw_title='Manual correction' WHERE id=%s", (perf,))
    store.commit()
    asyncio.run(music_jobs.enqueue(req.model_copy(update={'payload': {**req.payload, 'request_run': 'again'}})))
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM source_documents').fetchone()[0] == 1
    provider.comments.return_value = ([comment('00:30 Changed title\n02:10 Another title')], False)
    asyncio.run(music_jobs.enqueue(req.model_copy(update={'payload': {**req.payload, 'request_run': 'changed', 'extraction_version': '2'}})))
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT raw_title FROM performances WHERE id=%s', (perf,)).fetchone()[0] == 'Manual correction'
    assert store.execute('SELECT count(*) FROM performances').fetchone()[0] == 2
    assert store.execute('SELECT count(*) FROM performance_artists').fetchone()[0] == 1
    assert store.execute("SELECT count(*) FROM source_documents WHERE source_metadata->>'disposition'='review_candidate'").fetchone()[0] == 1


def test_pending_archive_can_fill_existing_empty_catalog_archive(store, provider):
    req, _ = queue(store, wait_count=3)
    video_id = row(store, 'videos', platform='youtube', platform_video_id='abcdefghijk',
                   source_account_id=req.external_account_id, title='Legacy import')
    archive_id = row(store, 'live_archives', video_id=video_id, setlist_state='unavailable')
    store.commit()
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT setlist_state FROM live_archives WHERE id=%s', (archive_id,)).fetchone()[0] == 'partial'
    assert store.execute('SELECT count(*) FROM performances WHERE archive_id=%s', (archive_id,)).fetchone()[0] == 2
    assert store.execute('SELECT count(*) FROM live_archives').fetchone()[0] == 1


def test_edit_during_provider_call_fences_write(store, provider):
    req, _ = queue(store)
    vid = row(store, 'videos', platform='youtube', platform_video_id='abcdefghijk', title='Manual title')
    store.commit()
    async def fetch(_):
        store.execute("UPDATE videos SET title='Concurrent edit' WHERE id=%s", (vid,))
        store.commit()
        return [video()]
    provider.videos.side_effect = fetch
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM live_archives').fetchone()[0] == 0
    assert store.execute("SELECT source_metadata->>'disposition' FROM source_documents").fetchone()[0] == 'version_conflict'
    assert store.execute('SELECT title FROM videos').fetchone()[0] == 'Concurrent edit'


def test_channel_mismatch_and_disabled_account_do_not_store(store, provider):
    req, _ = queue(store)
    provider.videos.return_value = [video(channel_id='UC'+'b'*22)]
    assert run()['status'] == 'failed'
    assert store.execute('SELECT count(*) FROM videos').fetchone()[0] == 0
    store.execute('UPDATE external_accounts SET collection_enabled=false')
    store.commit()
    with pytest.raises(ValueError):
        asyncio.run(music_jobs.enqueue(req))


def test_first_poll_baselines_history_then_new_end_queues_with_24h_delay(store, provider):
    req = request(store, kind='youtube_poll')
    asyncio.run(music_jobs.enqueue(req))
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT count(*) FROM worker_jobs WHERE job_type='youtube_collect'").fetchone()[0] == 0
    baseline = store.execute("SELECT provider_state->>'youtube_baseline_at' FROM collection_states").fetchone()[0]
    ended = datetime.now(UTC) + timedelta(seconds=1)
    provider.recent.return_value = ('uploads', [video(ended_at=ended)], False)
    asyncio.run(music_jobs.enqueue(req.model_copy(update={'payload': {**req.payload, 'request_run': 'next-poll'}})))
    assert run()['status'] == 'succeeded'
    due = store.execute("SELECT next_attempt_at FROM worker_jobs WHERE job_type='youtube_collect'").fetchone()[0]
    assert due == ended + timedelta(hours=24)
    assert store.execute("SELECT provider_state->>'youtube_baseline_at' FROM collection_states").fetchone()[0] == baseline
    asyncio.run(music_jobs.enqueue(req.model_copy(update={'payload': {**req.payload, 'request_run': 'poll-again'}})))
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT count(*) FROM worker_jobs WHERE job_type='youtube_collect'").fetchone()[0] == 1


def test_explicit_backfill_bypasses_baseline_only_for_selected_ids(store, provider):
    req = request(store, kind='youtube_poll')
    req = req.model_copy(update={'payload': {**req.payload, 'backfill_video_ids': ['abcdefghijk']}})
    asyncio.run(music_jobs.enqueue(req))
    assert run()['status'] == 'succeeded'
    provider.videos.assert_awaited_once_with(['abcdefghijk'])
    assert store.execute('SELECT count(*) FROM collection_states').fetchone()[0] == 0
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM live_archives').fetchone()[0] == 1


def test_cover_is_separate_and_does_not_invent_singer_or_song(store, provider):
    queue(store, purpose='cover')
    provider.videos.return_value = [video(title='Song / cover', started_at=None, ended_at=None)]
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM covers WHERE song_id IS NULL').fetchone()[0] == 1
    assert store.execute('SELECT count(*) FROM cover_artists').fetchone()[0] == 0
    assert store.execute('SELECT count(*) FROM live_archives').fetchone()[0] == 0
    provider.comments.assert_not_awaited()


@pytest.mark.parametrize('title,started,ended,scheduled,expected', [
    ('歌枠', True, True, False, 'archive'), ('KARAOKE STREAM', True, True, False, 'archive'),
    ('弾き語り', True, True, False, 'archive'), ('weekly chat', True, True, False, None),
    ('歌枠 cover', True, False, False, None), ('cover', False, False, True, None),
    ('歌ってみた', False, False, False, 'cover'), ('original single', False, False, False, None),
])
def test_video_boundaries(title, started, ended, scheduled, expected):
    now = datetime.now(UTC)
    assert purpose(video(title=title, started_at=now if started else None, ended_at=now if ended else None, scheduled=scheduled)) == expected


@pytest.mark.parametrize('status,reason,retry', [(401, 'authError', False), (403, 'forbidden', False),
    (403, 'commentsDisabled', False), (403, 'quotaExceeded', True), (404, 'videoNotFound', False),
    (429, 'rateLimit', True), (500, 'backendError', True)])
def test_adapter_sanitizes_errors_and_honors_retry_after(status, reason, retry):
    def respond(request):
        return httpx.Response(status, json={'error': {'errors': [{'reason': reason}], 'message': 'SECRET'}}, headers={'Retry-After': '120'})
    provider = YouTubeClient('SECRET', transport=httpx.MockTransport(respond), interval=0)
    with pytest.raises(YouTubeFailure) as failure:
        asyncio.run(provider.get('videos', id='abcdefghijk'))
    assert failure.value.retry == retry
    assert failure.value.retry_after >= 120
    assert 'SECRET' not in str(failure.value)


@pytest.mark.parametrize('body', [b'invalid json', b'[]', b'{}', b'{"items": {}}'])
def test_adapter_malformed_response(body):
    provider = YouTubeClient('fixture', transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)), interval=0)
    with pytest.raises(YouTubeFailure):
        asyncio.run(provider.get('videos'))


def test_comments_pagination_is_bounded_and_keeps_id_and_raw_text():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={'nextPageToken': 'again', 'items': [{'snippet': {'topLevelComment': {
            'id': 'comment-id', 'snippet': {'textOriginal': comment().text}}}}]})
    provider = YouTubeClient('fixture', transport=httpx.MockTransport(respond), interval=0)
    comments, truncated = asyncio.run(provider.comments('abcdefghijk'))
    assert len(calls) == 3 and truncated
    assert comments[0].id == 'comment-id' and comments[0].text == comment().text


def test_rules_and_url_boundary():
    rows = parse_setlist('00:00 START\n00:30 Song\n99:99 invalid\n01:20 Song 99.5点\n01:20 duplicate\n02:00 MC')
    assert [r['start_seconds'] for r in rows] == [30, 80]
    assert rows[1]['title'] == 'Song'
    assert parse_setlist('01:20 - 02:30 1曲目:「Quoted Song」 99.5点')[0]['title'] == 'Quoted Song'
    req = service.url_request(account_id=1, channel_id=CHANNEL, url='https://youtu.be/abcdefghijk')
    assert req.parsed_payload().youtube_video_id == 'abcdefghijk'
    with pytest.raises(ValueError):
        service.url_request(account_id=1, channel_id=CHANNEL, url='https://youtube.com.attacker.test/watch?v=abcdefghijk')


def test_scheduled_video_outside_recent_window_is_still_observed(store, provider):
    req = request(store, kind='youtube_poll')
    provider.recent.return_value = ('uploads', [video(started_at=None, ended_at=None, scheduled=True)], False)
    asyncio.run(music_jobs.enqueue(req))
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT provider_state->'youtube_pending_video_ids' FROM collection_states").fetchone()[0] == ['abcdefghijk']
    provider.recent.return_value = ('uploads', [], False)
    provider.videos.return_value = [video(ended_at=datetime.now(UTC)+timedelta(seconds=1))]
    asyncio.run(music_jobs.enqueue(req.model_copy(update={'payload': {**req.payload, 'request_run': 'later'}})))
    assert run()['status'] == 'succeeded'
    provider.videos.assert_awaited_once_with(['abcdefghijk'])
    assert store.execute("SELECT count(*) FROM worker_jobs WHERE job_type='youtube_collect'").fetchone()[0] == 1
    assert store.execute("SELECT provider_state->'youtube_pending_video_ids' FROM collection_states").fetchone()[0] == []


def test_failed_poll_does_not_initialize_baseline(store, provider):
    req = request(store, kind='youtube_poll')
    asyncio.run(music_jobs.enqueue(req))
    provider.recent.side_effect = YouTubeFailure('transport', retry=True)
    assert run()['status'] == 'retry'
    assert store.execute('SELECT count(*) FROM collection_states').fetchone()[0] == 0


def test_deactivated_account_has_no_provider_call(store, provider):
    queue(store)
    store.execute('UPDATE external_accounts SET collection_enabled=false')
    store.commit()
    assert run()['status'] == 'idle'
    provider.videos.assert_not_awaited()


def test_ai_extraction_requires_source_evidence_and_does_not_resolve_names(store, provider, monkeypatch):
    queue(store)
    monkeypatch.setattr(service, 'extract_youtube_setlist', AsyncMock(return_value=[
        {'timestamp': '00:30', 'title': 'Song One', 'original_artist': 'Original'},
        {'timestamp': '02:10', 'title': 'Imaginary song', 'original_artist': 'Imaginary artist'},
        {'timestamp': '59:59', 'title': 'Song One', 'original_artist': None},
    ]))
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT raw_title,raw_artist,song_id FROM performances').fetchall() == [('Song One', 'Original', None)]
    assert store.execute("SELECT source_metadata->>'extractor' FROM source_documents").fetchone()[0].startswith('openai:')


def test_adapter_normalizes_actual_start_and_duration_without_scheduled_fallback():
    response = {'items': [{'id': 'abcdefghijk', 'snippet': {'channelId': CHANNEL, 'title': 'Song', 'publishedAt': '2026-09-01T00:00:00Z'},
        'contentDetails': {'duration': 'PT1H2M3S'}, 'status': {'privacyStatus': 'public'},
        'liveStreamingDetails': {'scheduledStartTime': '2026-09-02T00:00:00Z'}}]}
    provider = YouTubeClient('fixture', transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)), interval=0)
    found = asyncio.run(provider.videos(['abcdefghijk']))[0]
    assert found.duration_seconds == 3723 and found.started_at is None and found.scheduled
    assert found.published_at.tzinfo is not None


def test_adapter_transport_timeout_is_retryable():
    def timeout(_):
        raise httpx.ReadTimeout('secret URL')
    provider = YouTubeClient('fixture', transport=httpx.MockTransport(timeout), interval=0)
    with pytest.raises(YouTubeFailure) as failure:
        asyncio.run(provider.videos(['abcdefghijk']))
    assert failure.value.retry and str(failure.value) == 'transport'


def test_new_youtube_modules_have_no_legacy_or_excluded_dependencies():
    import ast
    from pathlib import Path
    forbidden = ('app.core.db', 'app.integrations.youtube_live_archive', 'app.integrations.youtube_channel_monitor',
                 'app.integrations.karaoke', 'app.integrations.spotify_title_translation', 'app.lyrics_pipeline',
                 'app.agents', 'app.bots', 'app.services.x_collection', 'app.integrations.google')
    for file in ('app/integrations/youtube_catalog.py', 'app/services/youtube_collection.py', 'app/repositories/youtube_collection.py'):
        tree = ast.parse(Path(file).read_text(encoding='utf-8'))
        modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(module and module.startswith(forbidden) for module in modules)
