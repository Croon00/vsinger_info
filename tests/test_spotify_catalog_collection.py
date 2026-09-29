"""Registered Spotify collection through disposable PostgreSQL and fake providers."""
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
from test_music_jobs import store
from app.api.routers.read_api import router
from app.core.config import settings
from app.db.catalog_session import get_catalog_session
from app.integrations.spotify_catalog import ALBUM_GROUPS, SpotifyCatalogClient, SpotifyFailure, album_from_api
from app.integrations.youtube_catalog import Video
from app.schemas.worker_jobs import JobRequest
from app.services import music_jobs, spotify_collection as service


SINGER = 's' * 22
GUEST = 'g' * 22
ALBUM = 'a' * 22
SECOND = 'b' * 22
TRACK = 't' * 22
OTHER_TRACK = 'u' * 22
CHANNEL = 'UC' + 'c' * 22


def raw_track(id=TRACK, artists=(SINGER,), number=1):
    return dict(id=id, name='Original Track', disc_number=1, track_number=number,
                duration_ms=200000, artists=[dict(id=a) for a in artists])


def raw_album(id=ALBUM, artists=(SINGER,), tracks=1):
    return dict(id=id, name='Original Album', album_type='single', release_date='2026-09-01',
                release_date_precision='day', total_tracks=tracks,
                images=[{'url': 'https://i.scdn.co/image/fixture'}], artists=[dict(id=a) for a in artists])


def make_album(id=ALBUM, artists=(SINGER,), tracks=None):
    items = tracks if tracks is not None else [raw_track()]
    return album_from_api(raw_album(id=id, artists=artists, tracks=len(items)), items)


def register(db, spotify_id=SINGER, *, enabled=True, owner=True):
    artist = row(db, 'artists', entity_kind='solo', slug='artist-'+spotify_id[0],
                 name_native='Singer '+spotify_id[0], show_in_catalog=True)
    account = row(db, 'external_accounts', platform='spotify', platform_id=spotify_id,
                  url='https://open.spotify.com/artist/'+spotify_id, collection_enabled=enabled)
    if owner:
        row(db, 'artist_external_accounts', artist_id=artist, account_id=account, relationship='owner')
    db.commit()
    return artist, account


def request(account, **payload):
    return JobRequest(job_type='spotify_collect', external_account_id=account,
                      payload={'spotify_artist_id': SINGER, **payload})


@pytest.fixture
def provider(monkeypatch):
    fake = SimpleNamespace(albums_page=AsyncMock(return_value=([{'id': ALBUM}], False, None)),
                           album=AsyncMock(return_value=make_album()),
                           isrcs=AsyncMock(return_value={}),
                           credited_albums=AsyncMock(return_value=[]))
    monkeypatch.setattr(service, 'client', lambda: fake)
    return fake


def run():
    return asyncio.run(music_jobs.run_once(handlers=service.handlers(), min_interval_seconds=0))


def drain(limit=20):
    """Run jobs until the queue is idle; follow-up pages and album groups are separate jobs."""
    statuses = []
    for _ in range(limit):
        status = run()['status']
        if status == 'idle':
            return statuses
        statuses.append(status)
    raise AssertionError('queue did not drain')


def enqueue(account, **payload):
    return asyncio.run(music_jobs.enqueue(request(account, **payload)))


def test_registered_artist_release_and_track_reach_real_api(store, provider, monkeypatch):
    artist, account = register(store)
    enqueue(account)
    assert run()['status'] == 'succeeded'
    album = store.execute('SELECT id,spotify_album_id,title_native,release_year,release_month,release_day FROM albums').fetchone()
    assert album[1:] == (ALBUM, 'Original Album', 2026, 9, 1)
    recording = store.execute('SELECT id,song_id,title_native FROM recordings').fetchone()
    assert recording[1:] == (None, 'Original Track')
    assert store.execute('SELECT platform,external_id FROM recording_external_ids').fetchone() == ('spotify', TRACK)
    assert store.execute('SELECT count(*) FROM album_tracks').fetchone()[0] == 1
    receipt = store.execute("SELECT result_summary FROM catalog_imports WHERE source_kind='batch_import'").fetchone()[0]
    assert receipt['albums'][0]['raw']['id'] == ALBUM
    assert receipt['albums'][0]['tracks'][0]['raw']['id'] == TRACK
    app = FastAPI()
    app.include_router(router, prefix='/api')
    def session():
        with music_jobs.catalog_runtime_session() as current:
            yield current
    app.dependency_overrides[get_catalog_session] = session
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app) as api:
        api.headers['X-API-Key'] = 'fixture'
        listing = api.get(f'/api/artists/{artist}/albums')
        assert listing.status_code == 200, listing.text
        assert listing.json()[0]['name'] == 'Original Album'
        detail = api.get(f'/api/albums/{album[0]}')
        assert detail.status_code == 200, detail.text
        assert detail.json()['tracks'][0]['name'] == 'Original Track'
        assert detail.json()['tracks'][0]['song_id'] is None
    assert provider.albums_page.await_count == 1


def test_registered_joint_release_only_links_registered_credited_accounts(store, provider):
    first, account = register(store)
    second, _ = register(store, GUEST)
    provider.album.return_value = make_album(artists=(SINGER, GUEST), tracks=[raw_track(artists=(SINGER, GUEST))])
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert {r[0] for r in store.execute('SELECT artist_id FROM album_artists')} == {first, second}
    assert {r[0] for r in store.execute('SELECT artist_id FROM recording_artists')} == {first, second}
    assert store.execute('SELECT count(*) FROM external_accounts').fetchone()[0] == 2


def test_featured_track_release_is_visible_to_registered_source_artist(store, provider):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.services.catalog_read import CatalogRead
    artist, account = register(store)
    _, _ = register(store, GUEST)
    provider.album.return_value = make_album(artists=(GUEST,), tracks=[raw_track(artists=(SINGER, GUEST))])
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM album_artists WHERE artist_id=%s', (artist,)).fetchone()[0] == 0
    info = store.info
    engine = create_engine(f'postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}')
    try:
        with Session(engine) as session:
            assert len(CatalogRead(session).albums(artist)) == 1
    finally:
        engine.dispose()


def test_unregistered_cocredit_never_creates_account_or_artist(store, provider):
    artist, account = register(store)
    provider.album.return_value = make_album(artists=(SINGER, GUEST), tracks=[raw_track(artists=(SINGER, GUEST))])
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT artist_id FROM album_artists').fetchone()[0] == artist
    assert store.execute('SELECT artist_id FROM recording_artists').fetchone()[0] == artist
    assert store.execute('SELECT count(*) FROM artists').fetchone()[0] == 1


def test_uncredited_release_from_provider_is_skipped(store, provider):
    _, account = register(store)
    provider.album.return_value = make_album(artists=(GUEST,), tracks=[raw_track(artists=(GUEST,))])
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM albums').fetchone()[0] == 0
    assert store.execute("SELECT result_summary->'skipped_uncredited' FROM catalog_imports").fetchone()[0] == [ALBUM]


@pytest.mark.parametrize('change', ["UPDATE external_accounts SET collection_enabled=false",
    "UPDATE external_accounts SET archived_at=clock_timestamp()",
    "UPDATE external_accounts SET platform_id='wrong'", "DELETE FROM artist_external_accounts"])
def test_ineligible_account_never_calls_spotify(store, provider, change):
    _, account = register(store)
    store.execute(change)
    store.commit()
    try:
        enqueue(account)
    except ValueError:
        pass
    else:
        assert run()['status'] in ('idle', 'failed')
    provider.albums_page.assert_not_awaited()


def test_recollection_keeps_manual_edits_links_and_lyrics(store, provider):
    _, account = register(store)
    enqueue(account)
    assert run()['status'] == 'succeeded'
    album = store.execute('SELECT id FROM albums').fetchone()[0]
    recording = store.execute('SELECT id FROM recordings').fetchone()[0]
    song = row(store, 'songs', title_native='Approved song')
    row(store, 'recording_lyrics', recording_id=recording, original_lyrics='Approved lyrics', translation_ko='수동 번역')
    store.execute("UPDATE albums SET title_native='Manual album' WHERE id=%s", (album,))
    store.execute("UPDATE recordings SET title_native='Manual track',song_id=%s WHERE id=%s", (song, recording))
    store.commit()
    provider.album.return_value = make_album(tracks=[raw_track(), raw_track(OTHER_TRACK, number=2)])
    enqueue(account, request_run='recollect')
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT title_native FROM albums').fetchone()[0] == 'Manual album'
    assert store.execute('SELECT title_native,song_id FROM recordings').fetchone() == ('Manual track', song)
    assert store.execute('SELECT translation_ko FROM recording_lyrics').fetchone()[0] == '수동 번역'
    assert store.execute('SELECT count(*) FROM album_tracks').fetchone()[0] == 1
    assert store.execute("SELECT result_summary->'actions'->0->>'status' FROM catalog_imports ORDER BY id DESC LIMIT 1").fetchone()[0] == 'review_candidate'


def test_reuse_same_track_across_two_new_albums_without_duplication(store, provider):
    _, account = register(store)
    provider.albums_page.return_value = ([{'id': ALBUM}, {'id': SECOND}], False, None)
    provider.album.side_effect = [make_album(ALBUM), make_album(SECOND)]
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM albums').fetchone()[0] == 2
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 1
    assert store.execute('SELECT count(*) FROM album_tracks').fetchone()[0] == 2


def test_next_page_is_durable_and_uses_same_account(store, provider):
    _, account = register(store)
    provider.albums_page.return_value = ([{'id': ALBUM}], True, None)
    enqueue(account)
    assert run()['status'] == 'succeeded'
    pending = store.execute("SELECT payload,external_account_id FROM worker_jobs WHERE status='pending'").fetchone()
    assert pending[0]['album_offset'] == 10 and pending[1] == account
    provider.albums_page.return_value = ([], False, None)
    assert run()['status'] == 'succeeded'
    assert provider.albums_page.await_args_list[-1].kwargs['offset'] == 10


def test_provider_timeout_and_rate_limit_retry_without_partial_write(store, provider):
    _, account = register(store)
    provider.album.side_effect = SpotifyFailure('rate_limited', retry=True, retry_after=600)
    job = enqueue(account)
    assert run()['status'] == 'retry'
    assert store.execute('SELECT count(*) FROM albums').fetchone()[0] == 0
    assert asyncio.run(music_jobs.status(job))['next_attempt_at'] > datetime.now(UTC)+timedelta(minutes=9)


def test_account_change_during_fetch_rolls_back_all(store, provider):
    _, account = register(store)
    enqueue(account)
    async def altered(_):
        store.execute('UPDATE external_accounts SET collection_enabled=false WHERE id=%s', (account,))
        store.commit()
        return make_album()
    provider.album.side_effect = altered
    assert run()['status'] in ('lease_lost', 'failed')
    assert store.execute('SELECT count(*) FROM albums').fetchone()[0] == 0


def test_optional_youtube_matching_only_on_registered_channel(store, provider, monkeypatch):
    artist, account = register(store)
    youtube = row(store, 'external_accounts', platform='youtube', platform_id=CHANNEL,
                  url='https://youtube.com/channel/'+CHANNEL, collection_enabled=True)
    row(store, 'artist_external_accounts', artist_id=artist, account_id=youtube, relationship='owner')
    store.commit()
    item = Video(id='abcdefghijk', channel_id=CHANNEL, title='Original Track Official Music Video',
                 availability='public')
    fake = SimpleNamespace(get=AsyncMock(return_value={'items': [
        {'id': {'videoId': 'abcdefghijk'}, 'snippet': {'channelId': CHANNEL, 'title': item.title}}]}),
        videos=AsyncMock(return_value=[item]))
    monkeypatch.setattr(service, 'YouTubeClient', lambda *_: fake)
    monkeypatch.setattr(settings, 'youtube_api_key', 'fixture')
    enqueue(account, link_youtube=True)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT official_video_id FROM recordings').fetchone()[0] == store.execute('SELECT id FROM videos').fetchone()[0]
    assert store.execute('SELECT source_account_id FROM videos').fetchone()[0] == youtube
    fake.get.assert_awaited_once()


def test_ambiguous_youtube_candidates_are_held_without_link(store, provider, monkeypatch):
    artist, account = register(store)
    youtube = row(store, 'external_accounts', platform='youtube', platform_id=CHANNEL,
                  url='https://youtube.com/channel/'+CHANNEL, collection_enabled=True)
    row(store, 'artist_external_accounts', artist_id=artist, account_id=youtube, relationship='owner')
    store.commit()
    fake = SimpleNamespace(get=AsyncMock(return_value={'items': [
        {'id': {'videoId': external}, 'snippet': {'channelId': CHANNEL, 'title': 'Original Track Official MV'}}
        for external in ('abcdefghijk','lmnopqrstuv')]}), videos=AsyncMock())
    monkeypatch.setattr(service, 'YouTubeClient', lambda *_: fake)
    monkeypatch.setattr(settings, 'youtube_api_key', 'fixture')
    enqueue(account, link_youtube=True)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT official_video_id FROM recordings').fetchone()[0] is None
    assert store.execute('SELECT count(*) FROM videos').fetchone()[0] == 0
    assert store.execute("SELECT result_summary->'youtube_matches'->%s->>'status' FROM catalog_imports", (TRACK,)).fetchone()[0] == 'ambiguous_or_missing'
    fake.videos.assert_not_awaited()


def test_youtube_match_without_unique_registered_channel_records_reason(store, provider, monkeypatch):
    _, account = register(store)
    monkeypatch.setattr(service, 'YouTubeClient', lambda *_: (_ for _ in ()).throw(AssertionError('unexpected YouTube search')))
    enqueue(account, link_youtube=True)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT official_video_id FROM recordings').fetchone()[0] is None
    assert store.execute("SELECT result_summary->'youtube_matches'->%s->>'status' FROM catalog_imports", (TRACK,)).fetchone()[0] == 'no_unique_registered_youtube_channel'


def test_existing_other_account_video_is_not_claimed_for_spotify_track(store, provider, monkeypatch):
    artist, account = register(store)
    youtube = row(store, 'external_accounts', platform='youtube', platform_id=CHANNEL,
                  url='https://youtube.com/channel/'+CHANNEL, collection_enabled=True)
    other = row(store, 'external_accounts', platform='youtube', platform_id='UC'+'z'*22,
                url='https://youtube.com/channel/'+'UC'+'z'*22, collection_enabled=True)
    row(store, 'artist_external_accounts', artist_id=artist, account_id=youtube, relationship='owner')
    row(store, 'videos', platform='youtube', platform_video_id='abcdefghijk',
        title='Existing video', source_account_id=other)
    store.commit()
    item = Video(id='abcdefghijk', channel_id=CHANNEL, title='Original Track Official Music Video', availability='public')
    fake = SimpleNamespace(get=AsyncMock(return_value={'items': [
        {'id': {'videoId': item.id}, 'snippet': {'channelId': CHANNEL, 'title': item.title}}]}),
        videos=AsyncMock(return_value=[item]))
    monkeypatch.setattr(service, 'YouTubeClient', lambda *_: fake)
    monkeypatch.setattr(settings, 'youtube_api_key', 'fixture')
    enqueue(account, link_youtube=True)
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT official_video_id FROM recordings').fetchone()[0] is None
    assert store.execute('SELECT source_account_id FROM videos').fetchone()[0] == other
    assert store.execute("SELECT result_summary->'youtube_matches'->%s->>'status' FROM catalog_imports", (TRACK,)).fetchone()[0] == 'existing_video_conflict'


def test_default_sync_never_calls_youtube(store, provider, monkeypatch):
    _, account = register(store)
    monkeypatch.setattr(service, 'YouTubeClient', lambda *_: (_ for _ in ()).throw(AssertionError('unexpected YouTube search')))
    enqueue(account)
    assert run()['status'] == 'succeeded'


def test_operational_readiness_names_missing_credentials_without_values(store, monkeypatch):
    from app.services.worker_readiness import inspect_readiness
    from app.services.youtube_collection import handlers as youtube_handlers
    # The stage-2 store fixture deliberately empties the global registry.
    monkeypatch.setattr(music_jobs, 'HANDLERS', {**youtube_handlers(), **service.handlers()})
    monkeypatch.setattr(settings, 'runtime_cutover_enabled', True)
    monkeypatch.setattr(settings, 'agent_enabled', True)
    monkeypatch.setattr(settings, 'youtube_api_key', None)
    monkeypatch.setattr(settings, 'spotify_client_id', None)
    monkeypatch.setattr(settings, 'spotify_client_secret', None)
    row(store, 'external_accounts', platform='youtube', platform_id=CHANNEL,
        collection_enabled=True, url='https://example.com/channel')
    row(store, 'external_accounts', platform='spotify', platform_id=SINGER,
        collection_enabled=True, url='https://example.com/artist')
    store.commit()
    status = asyncio.run(inspect_readiness())
    assert not status.ready
    assert status.unimplemented_handlers == []
    assert set(status.missing_credentials) == {'YOUTUBE_API_KEY','SPOTIFY_CLIENT_ID','SPOTIFY_CLIENT_SECRET'}


@pytest.mark.parametrize('status,retry', [(401,False),(403,False),(404,False),(429,True),(500,True)])
def test_adapter_error_status_retry_after_and_no_secret_leak(status, retry):
    def respond(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200, json={'access_token': 'PRIVATE'})
        return httpx.Response(status, json={'error': 'PRIVATE'}, headers={'Retry-After': '120'})
    provider = SpotifyCatalogClient('CLIENT','SECRET',transport=httpx.MockTransport(respond),interval_seconds=0)
    with pytest.raises(SpotifyFailure) as failure:
        asyncio.run(provider.albums_page(SINGER, offset=0, group='album'))
    assert failure.value.retry == retry and failure.value.retry_after >= 120
    assert 'PRIVATE' not in str(failure.value) and 'SECRET' not in str(failure.value)


@pytest.mark.parametrize('body', [b'[]',b'garbage',b'{"items": {}}'])
def test_adapter_rejects_malformed_pages(body):
    def respond(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200,json={'access_token':'TOKEN'})
        return httpx.Response(200,content=body)
    provider = SpotifyCatalogClient('CLIENT','SECRET',transport=httpx.MockTransport(respond),interval_seconds=0)
    with pytest.raises(SpotifyFailure):
        asyncio.run(provider.albums_page(SINGER, offset=0, group='album'))


def test_adapter_timeout_is_retryable_and_page_size_is_ten():
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200,json={'access_token':'TOKEN'})
        raise httpx.ReadTimeout('PRIVATE')
    provider = SpotifyCatalogClient('CLIENT','SECRET',transport=httpx.MockTransport(respond),interval_seconds=0)
    with pytest.raises(SpotifyFailure) as failure:
        asyncio.run(provider.albums_page(SINGER, offset=10, group='album'))
    assert failure.value.retry
    assert calls[-1].url.params['limit'] == '10' and calls[-1].url.params['offset'] == '10'


def test_invalid_partial_release_date_fails_closed():
    with pytest.raises(ValueError):
        album_from_api({**raw_album(), 'release_date':'2026-02-30'}, [raw_track()])


def test_adapter_refuses_partial_album_tracks():
    def respond(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200,json={'access_token':'TOKEN'})
        if request.url.path.endswith('/tracks'):
            return httpx.Response(200,json={'items':[raw_track()], 'next':None})
        return httpx.Response(200,json=raw_album(tracks=2))
    provider = SpotifyCatalogClient('CLIENT','SECRET',transport=httpx.MockTransport(respond),interval_seconds=0)
    with pytest.raises(SpotifyFailure) as failure:
        asyncio.run(provider.album(ALBUM))
    assert str(failure.value) == 'incomplete_album'


def test_new_spotify_modules_have_no_legacy_or_excluded_dependency():
    import ast
    from pathlib import Path
    forbidden = ('app.core.db','app.integrations.spotify','app.integrations.spotify_youtube',
                 'app.integrations.spotify_title_translation','app.repositories.song_links',
                 'app.lyrics_pipeline','app.bots','app.agents')
    for file in ('app/integrations/spotify_catalog.py','app/services/spotify_collection.py','app/repositories/spotify_collection.py'):
        tree = ast.parse(Path(file).read_text(encoding='utf-8'))
        assert not any(node.module and any(node.module == name or node.module.startswith(name+'.') for name in forbidden)
                       for node in ast.walk(tree) if isinstance(node,ast.ImportFrom))



def test_adapter_isrcs_batches_without_market_and_rejects_relinked_ids():
    ids = [f'{n:022d}' for n in range(51)]
    calls = []
    def respond(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200, json={'access_token': 'TOKEN'})
        calls.append(dict(request.url.params))
        chunk = request.url.params['ids'].split(',')
        return httpx.Response(200, json={'tracks': [
            {'id': i, 'external_ids': {'isrc': 'jp-u90-26-02729' if i == ids[0] else ('bad' if i == ids[1] else None)}}
            for i in chunk]})
    provider = SpotifyCatalogClient('CLIENT', 'SECRET', transport=httpx.MockTransport(respond), interval_seconds=0)
    result = asyncio.run(provider.isrcs(ids + ids[:2]))
    assert [len(c['ids'].split(',')) for c in calls] == [50, 1] and all('market' not in c for c in calls)
    assert result[ids[0]] == 'JPU902602729' and result[ids[1]] is None and len(result) == 51
    def relinked(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200, json={'access_token': 'TOKEN'})
        return httpx.Response(200, json={'tracks': [{'id': 'z' * 22, 'external_ids': {'isrc': 'JPU902602729'}}]})
    provider = SpotifyCatalogClient('CLIENT', 'SECRET', transport=httpx.MockTransport(relinked), interval_seconds=0)
    with pytest.raises(SpotifyFailure, match='malformed_tracks'):
        asyncio.run(provider.isrcs([TRACK]))


def test_isrc_is_stored_and_joins_another_release_of_the_same_recording(store, provider):
    _, account = register(store)
    provider.isrcs.return_value = {TRACK: 'JPU902602729', OTHER_TRACK: 'JPU902602729'}
    enqueue(account)
    assert run()['status'] == 'succeeded'
    first = store.execute('SELECT id FROM recordings').fetchone()[0]
    store.execute("UPDATE recordings SET title_ko='수동 제목' WHERE id=%s", (first,))
    store.commit()
    # A later compilation carries the same recording under another Spotify track ID.
    provider.album.return_value = make_album(id=SECOND, tracks=[raw_track(id=OTHER_TRACK)])
    provider.albums_page.return_value = ([{'id': SECOND}], False, None)
    enqueue(account, request_run='second')
    assert run()['status'] == 'succeeded'
    assert store.execute('SELECT count(*) FROM recordings').fetchone()[0] == 1
    assert sorted(store.execute('SELECT recording_id,platform,external_id FROM recording_external_ids').fetchall()) == sorted([
        (first, 'spotify', TRACK), (first, 'isrc', 'JPU902602729'), (first, 'spotify', OTHER_TRACK)])
    assert store.execute('SELECT count(*) FROM album_tracks WHERE recording_id=%s', (first,)).fetchone()[0] == 2
    assert store.execute('SELECT title_ko FROM recordings').fetchone()[0] == '수동 제목'
    receipt = store.execute("SELECT result_summary FROM catalog_imports WHERE source_kind='batch_import' ORDER BY id DESC").fetchone()[0]
    assert {'album_id': SECOND, 'track_id': OTHER_TRACK, 'status': 'isrc_joined', 'isrc': 'JPU902602729'} in receipt['actions']


def test_isrc_held_by_archived_recording_is_recorded_not_moved(store, provider):
    _, account = register(store)
    old = row(store, 'recordings', title_native='Old')
    row(store, 'recording_external_ids', recording_id=old, platform='isrc', external_id='JPU902602729')
    store.execute('UPDATE recordings SET archived_at=clock_timestamp() WHERE id=%s', (old,))
    store.commit()
    provider.isrcs.return_value = {TRACK: 'JPU902602729'}
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT recording_id FROM recording_external_ids WHERE platform='isrc'").fetchall() == [(old,)]
    receipt = store.execute("SELECT result_summary FROM catalog_imports WHERE source_kind='batch_import'").fetchone()[0]
    assert any(a['status'] == 'isrc_conflict' for a in receipt['actions'])


def test_isrc_format_is_enforced_by_the_catalog(store):
    recording = row(store, 'recordings', title_native='R')
    store.commit()
    import psycopg
    for platform, value in (('isrc', 'jpu902602729'), ('isrc', 'JP-U90-26-02729'), ('spotify', 'short'), ('youtube', 'x' * 22)):
        with pytest.raises(psycopg.errors.CheckViolation):
            store.execute('INSERT INTO recording_external_ids(recording_id,platform,external_id) VALUES (%s,%s,%s)',
                          (recording, platform, value))
        store.rollback()



def test_adapter_reads_albums_in_the_japanese_market():
    seen = []
    def respond(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200, json={'access_token': 'TOKEN'})
        seen.append((request.url.path, request.url.params.get('market')))
        if request.url.path.endswith('/albums'):
            return httpx.Response(200, json={'items': [{'id': ALBUM}], 'next': None})
        if request.url.path.endswith('/tracks'):
            return httpx.Response(200, json={'items': [raw_track()], 'next': None})
        return httpx.Response(200, json=raw_album())
    provider = SpotifyCatalogClient('CLIENT', 'SECRET', transport=httpx.MockTransport(respond), interval_seconds=0)
    asyncio.run(provider.albums_page(SINGER, offset=0, group='album'))
    asyncio.run(provider.album(ALBUM))
    assert [market for _, market in seen] == ['JP', 'JP', 'JP']



def test_compilation_keeps_only_tracks_credited_to_registered_artists(store, provider):
    artist, account = register(store)
    provider.album.return_value = make_album(artists=('v' * 22,), tracks=[
        raw_track(id=TRACK, artists=(SINGER, 'x' * 22), number=1), raw_track(id=OTHER_TRACK, artists=('x' * 22,), number=2)])
    enqueue(account)
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT external_id FROM recording_external_ids WHERE platform='spotify'").fetchall() == [(TRACK,)]
    assert store.execute('SELECT count(*) FROM album_tracks').fetchone()[0] == 1
    receipt = store.execute("SELECT result_summary FROM catalog_imports WHERE source_kind='batch_import'").fetchone()[0]
    assert receipt['skipped_other_tracks'] == {ALBUM: [OTHER_TRACK]}
    # The artist's own release keeps every track, credited to them or not.
    provider.album.return_value = make_album(id=SECOND, tracks=[
        raw_track(id='w' * 22, number=1), raw_track(id='y' * 22, artists=('x' * 22,), number=2)])
    provider.albums_page.return_value = ([{'id': SECOND}], False, None)
    enqueue(account, request_run='own')
    assert run()['status'] == 'succeeded'
    assert store.execute("SELECT count(*) FROM recording_external_ids WHERE platform='spotify'").fetchone()[0] == 3


def test_search_pass_queues_credited_albums_missing_from_the_listing(store, provider):
    _, account = register(store)
    provider.credited_albums.return_value = [ALBUM, SECOND]      # ALBUM is also on the listing page
    provider.album.side_effect = lambda external: make_album(id=external, tracks=[
        raw_track(id=TRACK if external == ALBUM else OTHER_TRACK)])
    enqueue(account)
    assert set(drain()) == {'succeeded'}
    # Each album group is listed in its own job; only the last one runs the search pass.
    payloads = [r[0] for r in store.execute('SELECT payload FROM worker_jobs ORDER BY id')]
    assert [p['album_group'] for p in payloads if not p['album_ids']] == list(ALBUM_GROUPS)
    provider.credited_albums.assert_awaited_once_with(SINGER)
    assert [p['album_ids'] for p in payloads if p['album_ids']] == [[SECOND]]
    assert sorted(r[0] for r in store.execute('SELECT spotify_album_id FROM albums')) == sorted([ALBUM, SECOND])
    # A new run finds both albums stored and queues no album follow-up.
    enqueue(account, request_run='again')
    assert set(drain()) == {'succeeded'}
    assert store.execute("SELECT count(*) FROM worker_jobs WHERE jsonb_array_length(payload->'album_ids') > 0").fetchone()[0] == 1


def test_empty_listing_is_filled_by_the_search_pass(store, provider):
    _, account = register(store)
    provider.albums_page.return_value = ([], False, None)
    provider.credited_albums.return_value = [ALBUM]
    enqueue(account)
    assert set(drain()) == {'succeeded'}
    assert store.execute('SELECT spotify_album_id FROM albums').fetchall() == [(ALBUM,)]


def test_adapter_credited_albums_keeps_only_the_exact_artist_id():
    def respond(request):
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200, json={'access_token': 'TOKEN'})
        path = request.url.path
        if path.endswith('/top-tracks'):
            return httpx.Response(200, json={'tracks': [{'album': {'id': ALBUM}}]})
        if path == '/v1/search':
            kind = request.url.params['type']
            if kind == 'album':
                return httpx.Response(200, json={'albums': {'next': None, 'items': [
                    {'id': SECOND, 'artists': [{'id': SINGER}]}, {'id': 'z' * 22, 'artists': [{'id': GUEST}]}]}})
            return httpx.Response(200, json={'tracks': {'next': None, 'items': [
                {'artists': [{'id': GUEST}, {'id': SINGER}], 'album': {'id': 'c' * 22}}, {'artists': [{'id': GUEST}], 'album': {'id': 'd' * 22}}]}})
        return httpx.Response(200, json={'id': SINGER, 'name': 'Singer'})
    provider = SpotifyCatalogClient('CLIENT', 'SECRET', transport=httpx.MockTransport(respond), interval_seconds=0)
    assert asyncio.run(provider.credited_albums(SINGER)) == [ALBUM, SECOND, 'c' * 22]


def test_rate_limit_on_one_job_pauses_every_spotify_job(store, provider):
    _, account = register(store)
    _, other = register(store, GUEST)
    provider.albums_page.side_effect = SpotifyFailure('rate_limited', retry=True, retry_after=3600)
    enqueue(account)
    asyncio.run(music_jobs.enqueue(JobRequest(job_type='spotify_collect', external_account_id=other,
                                              payload={'spotify_artist_id': GUEST})))
    assert run()['status'] == 'retry'
    status, error = store.execute("SELECT status,last_error FROM worker_jobs WHERE external_account_id=%s", (account,)).fetchone()
    assert (status, error) == ('retry', 'rate_limited')
    assert run()['status'] == 'idle'                      # the other account's job waits too
    assert provider.albums_page.await_count == 1
    store.execute("UPDATE worker_jobs SET next_attempt_at=clock_timestamp() WHERE last_error='rate_limited'")
    store.commit()
    provider.albums_page.side_effect = None
    assert run()['status'] == 'succeeded'                 # pause ends at the provider's Retry-After


def _album_tracks(store, artist):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.services.catalog_read import CatalogRead
    info = store.info
    engine = create_engine(f'postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}')
    try:
        with Session(engine) as session:
            read = CatalogRead(session)
            return read.album(int(read.albums(artist)[0]['id']))['tracks']
    finally:
        engine.dispose()


def test_own_album_keeps_every_track_under_its_spotify_performers(store, provider):
    # HARMONICS case: the artist's own album holds a guest track and another person's remix.
    artist, account = register(store)
    provider.album.return_value = make_album(tracks=[
        {**raw_track(id=TRACK, number=1), 'artists': [{'id': SINGER, 'name': 'SINGER SPOTIFY'}]},
        {**raw_track(id=OTHER_TRACK, number=2), 'artists': [{'id': GUEST, 'name': 'Guest'}, {'id': 'x' * 22, 'name': 'Remixer'}]}])
    enqueue(account)
    assert set(drain()) == {'succeeded'}
    credits = store.execute('SELECT track_id,position,provider_artist_id,name FROM recording_provider_credits ORDER BY track_id,position').fetchall()
    assert credits == [(TRACK, 0, SINGER, 'SINGER SPOTIFY'), (OTHER_TRACK, 0, GUEST, 'Guest'), (OTHER_TRACK, 1, 'x' * 22, 'Remixer')]
    assert store.execute('SELECT count(*) FROM recording_artists').fetchone()[0] == 1     # still registered artists only
    assert store.execute('SELECT count(*) FROM artists').fetchone()[0] == 1
    tracks = _album_tracks(store, artist)
    # A registered performer shows the catalog names; an unregistered one Spotify's name.
    assert tracks[0]['artists'] == [{'artist_id': artist, 'name': 'Singer s', 'name_ko': None}]
    assert tracks[1]['artists'] == [{'artist_id': None, 'name': 'Guest', 'name_ko': None},
                                    {'artist_id': None, 'name': 'Remixer', 'name_ko': None}]


def test_recollection_backfills_provider_credits_of_stored_tracks(store, provider):
    artist, account = register(store)
    enqueue(account)
    assert set(drain()) == {'succeeded'}
    store.execute('DELETE FROM recording_provider_credits')                  # stored before revision 006
    store.commit()
    # Without provider credits the registered recording credits are shown.
    assert _album_tracks(store, artist)[0]['artists'] == [{'artist_id': artist, 'name': 'Singer s', 'name_ko': None}]
    enqueue(account, request_run='credits')
    assert set(drain()) == {'succeeded'}
    assert store.execute('SELECT track_id,provider_artist_id FROM recording_provider_credits').fetchall() == [(TRACK, SINGER)]
    assert store.execute('SELECT count(*) FROM albums').fetchone()[0] == 1
    receipts = [r[0] for r in store.execute("SELECT result_summary FROM catalog_imports WHERE source_kind='batch_import' ORDER BY id")]
    assert {'album_id': ALBUM, 'status': 'review_candidate', 'credited_tracks': 1} in receipts[len(ALBUM_GROUPS)]['actions']


def test_listing_that_ends_before_its_total_records_a_shortfall(store, provider):
    _, account = register(store)
    provider.albums_page.return_value = ([{'id': ALBUM}], False, 5)
    enqueue(account)
    assert set(drain()) == {'succeeded'}
    listings = [r[0] for r in store.execute("SELECT result_summary->'listing' FROM catalog_imports WHERE source_kind='batch_import' ORDER BY id")]
    assert [(l['group'], l['items'], l['total'], l['shortfall']) for l in listings] == [(g, 1, 5, 4) for g in ALBUM_GROUPS]


def test_adapter_lists_one_album_group_with_its_total():
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.host == 'accounts.spotify.com':
            return httpx.Response(200, json={'access_token': 'TOKEN'})
        return httpx.Response(200, json={'items': [{'id': ALBUM}], 'next': None, 'total': 7})
    provider = SpotifyCatalogClient('CLIENT', 'SECRET', transport=httpx.MockTransport(respond), interval_seconds=0)
    assert asyncio.run(provider.albums_page(SINGER, offset=0, group='appears_on')) == ([{'id': ALBUM}], False, 7)
    assert calls[-1].url.params['include_groups'] == 'appears_on'
    with pytest.raises(ValueError):
        asyncio.run(provider.albums_page(SINGER, offset=0, group='album,single'))