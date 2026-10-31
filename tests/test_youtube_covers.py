"""Cover reads and resumable imports: disposable PostgreSQL and fake YouTube only."""
import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_catalog_migration import local_server, database, row
from test_new_catalog_read import store, seed
from app.api.routers.read_api import router
from app.core.config import settings
from app.db.catalog_session import get_catalog_session
from app.integrations.youtube_catalog import Video, YouTubeClient
from app.services import youtube_cover_backfill as importer
from app.services.catalog_read import CatalogRead

CHANNEL = 'UC' + 'a' * 22


def test_shared_uploads_route_to_exact_registered_origin_without_rewriting(monkeypatch):
    primary='UCwuS0uY-Z2Gr_5OV2oFybFA'
    origin='UC3cuxhq3Cv-9h5wNXvWHspg'
    accounts=[dict(id=5,platform_id=primary),dict(id=105,platform_id=origin)]
    @contextmanager
    def session():
        yield object()
    saved=[]
    monkeypatch.setattr(importer,'catalog_runtime_session',session)
    monkeypatch.setattr(importer,'targets',lambda session:accounts)
    def persist(session,account,videos):
        saved.extend((account['id'],v.channel_id,v.id) for v in videos)
        return len(videos)
    monkeypatch.setattr(importer,'persist_page',persist)
    video=Video(id='utHgT3i8Dj8',channel_id=origin,title='Revival (Cover) / KMNZ NERO')
    foreign=video.model_copy(update={'id':'abcdefghijk','channel_id':CHANNEL})
    assert importer.save_page(accounts[0],[video,foreign])==1
    assert saved==[(105,origin,'utHgT3i8Dj8')]


def test_cover_api_owner_scope_pagination_visibility_and_auth(store, monkeypatch):
    db, engine = store
    artist, guest, *_ = seed(db)
    account = db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s', (artist,)).fetchone()[0]
    for index in range(3):
        video = row(db, 'videos', platform='youtube', platform_video_id=f'cover{index:06}', source_account_id=account,
                    title=f'歌ってみた {index}', published_at=f'2026-01-0{index+1}T00:00:00Z', duration_seconds=240,
                    availability='private' if index == 2 else 'public')
        row(db, 'covers', video_id=video)
    db.commit()
    app = FastAPI()
    app.include_router(router, prefix='/api')
    monkeypatch.setattr(settings, 'api_key', 'test')
    def session():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_catalog_session] = session
    with TestClient(app) as client:
        path = f'/api/artists/{artist}/covers'
        assert client.get(path).status_code == 401
        client.headers['X-API-Key'] = 'test'
        page = client.get(path + '?limit=1').json()
        assert page['total'] == 2
        assert page['items'][0]['title'] == '歌ってみた 1'
        assert client.get(path + '?offset=1&limit=1').json()['items'][0]['title'] == '歌ってみた 0'
        assert client.get(path + '?offset=10').json()['total'] == 2
        assert client.get(f'/api/artists/{guest}/covers').json()['total'] == 0
        assert client.get('/api/artists/999999/covers').status_code == 404
        assert client.get(path + '?limit=101').status_code == 422


def test_save_page_preserves_raw_source_deduplicates_and_excludes_live(store, monkeypatch):
    db, engine = store
    artist, *_ = seed(db)
    account = db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s', (artist,)).fetchone()[0]
    db.execute('UPDATE external_accounts SET collection_enabled=true,platform_id=%s WHERE id=%s', (CHANNEL, account))
    db.commit()
    @contextmanager
    def session():
        with Session(engine) as s:
            yield s
            s.commit()
    monkeypatch.setattr(importer, 'catalog_runtime_session', session)
    video = Video(id='abcdefghij1', channel_id=CHANNEL, title='Song cover', description='original description', availability='public')
    live = video.model_copy(update=dict(id='abcdefghij2', started_at=datetime.now(UTC)))
    foreign = video.model_copy(update=dict(id='abcdefghij3', channel_id='UC' + 'b'*22))
    target = dict(id=account, platform_id=CHANNEL)
    assert importer.save_page(target, [video, live, foreign]) == 1
    assert importer.save_page(target, [video]) == 0
    assert db.execute('SELECT count(*) FROM covers').fetchone()[0] == 1
    assert db.execute('SELECT count(*) FROM cover_artists').fetchone()[0] == 0
    assert db.execute("SELECT content_text FROM source_documents WHERE external_id='abcdefghij1'").fetchone()[0] == 'original description'
    # Earlier imports may have recorded a premiere as a live without provenance.
    # Add the cover while preserving the live and its performances.
    legacy=row(db,'videos',platform='youtube',platform_video_id='abcdefghij4',
               title='Song cover',availability='public',duration_seconds=240)
    row(db,'live_archives',video_id=legacy,primary_artist_id=artist)
    db.commit()
    premiere=video.model_copy(update=dict(id='abcdefghij4',duration_seconds=240,
        started_at=datetime(2026,1,1,tzinfo=UTC),ended_at=datetime(2026,1,1,0,6,tzinfo=UTC)))
    assert importer.save_page(target,[premiere])==1
    assert importer.save_page(target,[premiere])==0
    assert db.execute('SELECT source_account_id FROM videos WHERE id=%s',(legacy,)).fetchone()[0]==account
    assert db.execute('SELECT count(*) FROM live_archives WHERE video_id=%s',(legacy,)).fetchone()[0]==1


def test_budget_counts_failed_requests_and_stops_before_network():
    calls = []
    state = {}
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={'items': []})
    provider = importer.BudgetClient('fake', state, lambda: None, budget=1, interval=0)
    provider.transport = httpx.MockTransport(respond)
    asyncio.run(provider.get('channels'))
    with pytest.raises(importer.BudgetReached):
        asyncio.run(provider.get('channels'))
    assert len(calls) == len(state['requests']) == 1


def test_backfill_resumes_page_and_skips_completed_channel(tmp_path, monkeypatch):
    class Guard:
        def execute(self, *_): return self
        def scalar_one(self): return True
    @contextmanager
    def session(): yield Guard()
    monkeypatch.setattr(importer, 'catalog_runtime_session', session)
    monkeypatch.setattr(importer, 'verify_catalog_identity', lambda _: 'fixture')
    monkeypatch.setattr(importer, 'targets', lambda _: [dict(id=1, platform_id=CHANNEL)])
    monkeypatch.setattr(importer, 'save_page', lambda *_: 1)
    seen = []
    async def get(self, resource, **params):
        seen.append((resource, params))
        if resource == 'channels':
            return {'items': [dict(id=CHANNEL, contentDetails={'relatedPlaylists': {'uploads': 'uploads'}})]}
        return {'items': [], **({'nextPageToken': 'next'} if 'pageToken' not in params else {})}
    monkeypatch.setattr(importer.BudgetClient, 'get', get)
    path = tmp_path / 'progress.json'
    result = asyncio.run(importer.backfill('fake', path, max_pages=1))
    assert result['paused'] and result['completed'] == 0
    result = asyncio.run(importer.backfill('fake', path, max_pages=1))
    assert result['completed'] == 1 and seen[-1][1]['pageToken'] == 'next'
    count = len(seen)
    assert asyncio.run(importer.backfill('fake', path))['completed'] == 1
    assert len(seen) == count
    assert json.loads(path.read_text())['channels'][CHANNEL]['done']
