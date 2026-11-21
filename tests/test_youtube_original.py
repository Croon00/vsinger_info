"""Daily original classification and worker boundaries; no real provider calls."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from app.integrations.youtube_catalog import Video
from app.schemas.worker_jobs import JobRequest
from app.services import youtube_collection as service
from app.services.youtube_original import decide, eligible
from test_music_jobs import store, request, CHANNEL
from test_catalog_migration import row, database, local_server
from test_phase4_runtime import runtime_store
from app.services import music_jobs


def video(**updates):
    return Video(**{**dict(id='abcdefghijk', channel_id=CHANNEL,
        title='Artist「New Song」[Original]', description='Vocal: Artist',
        published_at=datetime.now(UTC)-timedelta(days=1), duration_seconds=180,
        availability='public'), **updates})


def scope(recordings=None):
    return {'owners': [{'id': 1, 'aliases': ['Artist', '歌手']}], 'recordings': recordings or []}


def recording(**updates):
    return {**dict(id=9, version=2, title_native='New Song', duration_ms=180000,
        official_video_id=None, aliases=['Artist'], channels={CHANNEL: 1}, albums=[]), **updates}


@pytest.mark.parametrize('title', ['Artist「New Song」[Original]', '【オリジナル曲】Artist「New Song」'])
def test_explicit_original_requires_exact_vocal_identity(title):
    result = decide(video(title=title), scope())
    assert result.status == 'new_original' and result.artist_ids == [1]
    assert result.title == 'New Song'


def test_markerless_release_matches_without_spotify_requirement():
    # Repository recordings may come from either reviewed YouTube imports or
    # Spotify. Neither a provider ID nor an official/original title tag is used.
    result = decide(video(title='New Song / Artist', description=''), scope([recording()]))
    assert result.status == 'link_recording' and result.recording_id == 9
    assert result.recording_version == 2


def test_description_can_establish_original_without_title_marker():
    result = decide(video(title='Artist「New Song」', description='オリジナル曲「New Song」\nVocal: Artist'), scope())
    assert result.status == 'new_original'
    assert decide(video(title='Artist「New Song」', description='原曲: オリジナル曲「New Song」\nVocal: Artist'), scope()).status == 'review_required'


@pytest.mark.parametrize('title', ['【オリジナルMV】Song / Artist', 'Song / Artist [Original MV]'])
def test_original_visuals_do_not_establish_original_composition(title):
    assert decide(video(title=title), scope()).status == 'review_required'


@pytest.mark.parametrize('updates', [
    {'duration_seconds': 30}, {'title': 'Song [Original] short.ver'},
    {'title': 'Song [Original] (1Chorus ver.)'}, {'title': 'Song [Original] ティザー'},
    {'title': 'Song [Original] MV公開中！'},
])
def test_promotional_clips_do_not_become_recordings(updates):
    assert decide(video(**updates), scope()).status == 'not_eligible'


@pytest.mark.parametrize('updates', [
    {'title': 'New Song Official Music Video'},
    {'description': ''},
    {'description': 'Vocal: Different Artist'},
    {'description': 'Vocal: Artist & Unregistered Guest'},
    {'description': 'Vocal: Artist remix'},
])
def test_official_label_or_unresolved_singer_does_not_create_original(updates):
    assert decide(video(**updates), scope()).status == 'review_required'


@pytest.mark.parametrize('updates', [
    {'title': 'New Song cover [Original]'}, {'title': 'New Song [Original] teaser'},
    {'title': 'New Song [Original] #shorts'}, {'title': 'New Song [Original] (Live ver.)'},
    {'title': '歌枠 New Song [Original]'}, {'availability': 'private'},
    {'scheduled': True}, {'started_at': datetime.now(UTC)},
])
def test_non_song_versions_and_active_broadcasts_are_excluded(updates):
    assert not eligible(video(**updates))
    assert decide(video(**updates), scope([recording()])).status == 'not_eligible'


def test_existing_manual_link_and_ambiguous_releases_are_preserved():
    sample = video(title='New Song / Artist')
    assert decide(sample, scope([recording(official_video_id='otherVideo1')])).reason == 'existing_official_video_preserved'
    assert decide(sample, scope([recording(), recording(id=10)])).reason == 'multiple_release_matches'
    assert decide(video(), scope() | {'owners': []}).reason == 'registered_owner_required'


def test_daily_poll_sends_markerless_upload_to_original_review_without_changing_cover(monkeypatch):
    from app.repositories import youtube_collection as repository
    monkeypatch.setattr(repository, 'poll_state', lambda *_: {'provider_state': {}, 'last_polled_at': None})
    async def db_call(fn, *args):
        return fn(None, *args)
    monkeypatch.setattr(service, 'client', lambda: SimpleNamespace(recent=AsyncMock(return_value=(
        'uploads', [video(title='New Song / Artist'), video(id='abcdefghij0', title='Song cover')], False))))
    monkeypatch.setattr(music_jobs, 'db_call', db_call)
    result = asyncio.run(service.collect_poll(SimpleNamespace(external_account_id=1),
        SimpleNamespace(backfill_video_ids=[], channel_id=CHANNEL)))
    assert result['purposes'] == {'abcdefghijk': 'original', 'abcdefghij0': 'cover'}
    assert service.handlers()['youtube_poll'].poll_interval_seconds == service.settings.youtube_poll_interval_seconds


def test_original_collection_uses_no_comments_or_model(monkeypatch):
    from app.repositories import youtube_original as repo
    monkeypatch.setattr(repo, 'scope', lambda *_: scope())
    async def db_call(fn, *args):
        if fn is repo.scope:
            return scope()
        return {'video': None, 'archive': None, 'cover': None}
    monkeypatch.setattr(music_jobs, 'db_call', db_call)
    provider = SimpleNamespace(videos=AsyncMock(return_value=[video()]), comments=AsyncMock(side_effect=AssertionError()))
    monkeypatch.setattr(service, 'client', lambda: provider)
    monkeypatch.setattr(service, 'select_setlist', AsyncMock(side_effect=AssertionError()))
    payload = JobRequest(job_type='youtube_collect', external_account_id=1,
        payload={'channel_id': CHANNEL, 'youtube_video_id': 'abcdefghijk', 'purpose': 'original'}).parsed_payload()
    result = asyncio.run(service.collect_video(SimpleNamespace(external_account_id=1), payload))
    assert result['outcome'] == 'collected' and result['original']['status'] == 'new_original'
    provider.comments.assert_not_awaited()
    service.select_setlist.assert_not_awaited()


def test_original_round_trip_is_audited_visible_and_idempotent(store, monkeypatch):
    from app.repositories.youtube_original import scope as get_scope
    req = request(store)
    artist = row(store, 'artists', slug='original-owner', name_native='Artist', entity_kind='solo', show_in_catalog=True)
    row(store, 'artist_external_accounts', artist_id=artist, account_id=req.external_account_id, relationship='owner')
    store.commit()
    req = req.model_copy(update={'payload': {**req.payload, 'purpose': 'original'}})
    provider = SimpleNamespace(videos=AsyncMock(return_value=[video()]), comments=AsyncMock(side_effect=AssertionError()))
    monkeypatch.setattr(service, 'client', lambda: provider)
    first = asyncio.run(music_jobs.enqueue(req))
    assert asyncio.run(music_jobs.run_once(handlers=service.handlers(), min_interval_seconds=0))['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 1
    assert store.execute('SELECT artist_id FROM recording_artists').fetchone()[0] == artist
    assert store.execute("SELECT count(*) FROM catalog_changes WHERE entity_type='recordings'").fetchone()[0] == 1
    assert store.execute('SELECT count(*) FROM live_archives').fetchone()[0] == 0
    assert store.execute('SELECT count(*) FROM covers').fetchone()[0] == 0
    # An explicit rerun uses a new job but must preserve the same recording.
    second = req.model_copy(update={'payload': {**req.payload, 'request_run': 'explicit-repeat'}})
    asyncio.run(music_jobs.enqueue(second))
    assert asyncio.run(music_jobs.run_once(handlers=service.handlers(), min_interval_seconds=0))['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 1
    from app.services.catalog_read import CatalogRead
    with music_jobs.catalog_runtime_session() as session:
        assert get_scope(session, req.external_account_id)['owners'][0]['id'] == artist
        page = CatalogRead(session).explore_songs(kind='original', agency='all', q='', order='latest', offset=0, limit=10)
        assert page['items'][0]['youtube_video_id'] == 'abcdefghijk'


def test_markerless_collection_links_existing_recording_instead_of_duplicating(store, monkeypatch):
    req = request(store)
    artist = row(store, 'artists', slug='release-owner', name_native='Artist', entity_kind='solo')
    row(store, 'artist_external_accounts', artist_id=artist, account_id=req.external_account_id, relationship='owner')
    recording_id = row(store, 'recordings', title_native='New Song', duration_ms=180000)
    row(store, 'recording_artists', recording_id=recording_id, artist_id=artist, role='primary')
    store.commit()
    req = req.model_copy(update={'payload': {**req.payload, 'purpose': 'original'}})
    monkeypatch.setattr(service, 'client', lambda: SimpleNamespace(videos=AsyncMock(return_value=[
        video(title='New Song / Artist', description='')]), comments=AsyncMock(side_effect=AssertionError())))
    asyncio.run(music_jobs.enqueue(req))
    result = asyncio.run(music_jobs.run_once(handlers=service.handlers(), min_interval_seconds=0))
    assert result['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 1
    linked = store.execute('SELECT official_video_id FROM recordings WHERE id=%s', (recording_id,)).fetchone()[0]
    assert linked is not None
    assert store.execute("SELECT action FROM catalog_changes WHERE entity_type='recordings'").fetchone()[0] == 'update'


def test_daily_poll_preserves_baseline_and_queues_original_with_existing_interval(store, monkeypatch):
    req = request(store, kind='youtube_poll')
    baseline = (datetime.now(UTC)-timedelta(days=3)).isoformat()
    import json
    store.execute('INSERT INTO collection_states(external_account_id,provider_state) VALUES (%s,%s::jsonb)',
                  (req.external_account_id, json.dumps({'youtube_baseline_at': baseline})))
    store.commit()
    old = video(id='abcdefghij0', published_at=datetime.now(UTC)-timedelta(days=4))
    monkeypatch.setattr(service, 'client', lambda: SimpleNamespace(recent=AsyncMock(return_value=(
        'uploads', [video(title='New Song / Artist'), old], False))))
    asyncio.run(music_jobs.enqueue(req))
    result = asyncio.run(music_jobs.run_once(handlers=service.handlers(), kinds=('youtube_poll',), min_interval_seconds=0))
    assert result['status'] == 'succeeded'
    jobs = store.execute("SELECT payload FROM worker_jobs WHERE job_type='youtube_collect'").fetchall()
    assert len(jobs) == 1 and jobs[0][0]['purpose'] == 'original'
    assert jobs[0][0]['youtube_video_id'] == 'abcdefghijk'
    assert store.execute('SELECT provider_state->>\'youtube_baseline_at\' FROM collection_states WHERE external_account_id=%s',
                         (req.external_account_id,)).fetchone()[0] == baseline


@pytest.mark.parametrize('existing_kind', ['covers', 'live_archives'])
def test_original_never_reclassifies_existing_cover_or_archive(store, monkeypatch, existing_kind):
    req = request(store)
    artist = row(store, 'artists', slug='preserved-owner', name_native='Artist', entity_kind='solo')
    row(store, 'artist_external_accounts', artist_id=artist, account_id=req.external_account_id, relationship='owner')
    stored_video = row(store, 'videos', platform='youtube', platform_video_id='abcdefghijk',
                       title='Existing classification', source_account_id=req.external_account_id)
    row(store, existing_kind, video_id=stored_video)
    store.commit()
    req = req.model_copy(update={'payload': {**req.payload, 'purpose': 'original'}})
    monkeypatch.setattr(service, 'client', lambda: SimpleNamespace(videos=AsyncMock(return_value=[video()])))
    asyncio.run(music_jobs.enqueue(req))
    assert asyncio.run(music_jobs.run_once(handlers=service.handlers(), min_interval_seconds=0))['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 0
    assert store.execute(f'SELECT count(*) FROM {existing_kind}').fetchone()[0] == 1


def test_owner_change_during_collection_keeps_original_as_review_candidate(store, monkeypatch):
    from app.repositories import youtube_collection as repository
    req = request(store)
    artist = row(store, 'artists', slug='changed-owner', name_native='Artist', entity_kind='solo')
    row(store, 'artist_external_accounts', artist_id=artist, account_id=req.external_account_id, relationship='owner')
    store.commit()
    req = req.model_copy(update={'payload': {**req.payload, 'purpose': 'original'}})
    monkeypatch.setattr(service, 'client', lambda: SimpleNamespace(videos=AsyncMock(return_value=[video()])))
    async def collect_then_change(job, payload):
        value = await service.collect_video(job, payload)
        assert value['original']['status'] == 'new_original'
        store.execute('DELETE FROM artist_external_accounts WHERE artist_id=%s', (artist,))
        store.commit()
        return value
    asyncio.run(music_jobs.enqueue(req))
    handler = music_jobs.Handler(collect_then_change, repository.persist_collect)
    assert asyncio.run(music_jobs.run_once(handlers={'youtube_collect': handler}, min_interval_seconds=0))['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 0
    assert store.execute("SELECT source_metadata->>'disposition' FROM source_documents").fetchone()[0] == 'version_conflict'


@pytest.mark.parametrize('credit', ['Vocal & Movie - Artist', 'Vocal Artist', '歌唱 Artist', '■Vocal：Artist'])
def test_official_credit_formats_preserve_exact_singer(credit):
    result = decide(video(title='Artist「New Song」Official MV', description=credit+'\n#オリジナル曲'), scope())
    assert result.status == 'new_original' and result.artist_ids == [1]


def test_editor_credit_is_not_singing_and_group_members_do_not_invent_individual_credits():
    assert decide(video(description='Vocal Editor: Artist'), scope()).reason == 'explicit_vocal_credit_required'
    grouped = {'owners': [{'id': 1, 'kind': 'group', 'aliases': ['Group']}], 'recordings': []}
    assert decide(video(description='歌唱 Group (Member A, Member B)'), grouped).artist_ids == [1]
    assert decide(video(description='歌唱 Group (feat. Unregistered Guest)'), grouped).status == 'review_required'


def test_original_hash_tag_does_not_override_cover_or_unrelated_quoted_song():
    assert decide(video(description='Vocal: Artist\n#cover #originalsong'), scope()).reason == 'description_cover_marker'
    assert decide(video(title='Other Song / Artist', description='オリジナル曲「Song」\nVocal: Artist'), scope()).status == 'review_required'
