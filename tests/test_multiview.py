"""Live snapshots and read contracts; fake providers and disposable local PostgreSQL only."""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from test_catalog_migration import database, local_server, apply, row
from app.api.routers.read_api import router, catalog
from app.core.config import settings
from app.integrations.youtube_catalog import Video
from app.repositories.youtube_collection import persist_poll
from app.services.catalog_read import CatalogRead

CHANNEL = 'UC' + 'a' * 22


def test_archive_poll_preserves_live_monitor_snapshot_and_backfill_preserves_state():
    now = datetime.now(UTC)
    def video(id, **kwargs):
        return Video(id=id, channel_id=CHANNEL, title='Stream', availability='public', **kwargs)
    session = Mock()
    value = dict(state={'provider_state': {}}, captured_at=now, playlist='uploads', truncated=False, gap=False,
                 purposes={}, videos=[video('aaaaaaaaaaa', started_at=now),
                    video('bbbbbbbbbbb', scheduled=True),
                    video('ccccccccccc', started_at=now, ended_at=now),
                    video('ddddddddddd', started_at=now).model_copy(update={'availability': 'private'})])
    persist_poll(session, SimpleNamespace(external_account_id=1), SimpleNamespace(backfill_video_ids=[]), value)
    state = json.loads(session.execute.call_args.args[1]['state'])
    assert 'youtube_live_snapshot' not in state
    assert 'youtube_live_monitor' not in state
    session.reset_mock()
    persist_poll(session, SimpleNamespace(external_account_id=1), SimpleNamespace(backfill_video_ids=['aaaaaaaaaaa']), value)
    session.execute.assert_not_called()


def test_stream_endpoint_validates_paging_and_preserves_auth(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix='/api')
    service = Mock(query_ms=0, query_count=0)
    service.live_streams.return_value = dict(items=[], total=0, offset=0, limit=100)
    service.stream_groups.return_value = [dict(key='group:1', name='Group', kind='group', account_ids=[1, 2])]
    app.dependency_overrides[catalog] = lambda: service
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app) as client:
        assert client.get('/api/streams').status_code == 401
        assert client.get('/api/stream-groups').status_code == 401
        client.headers['X-API-Key'] = 'fixture'
        assert client.get('/api/streams?limit=101').status_code == 422
        assert client.get('/api/streams?offset=-1').status_code == 422
        response = client.get('/api/streams')
        assert response.status_code == 200
        assert response.json()['items'] == []
        service.live_streams.assert_called_once_with(0, 100, False)
        client.get('/api/streams?include_upcoming=true')
        service.live_streams.assert_called_with(0, 100, True)
        assert client.get('/api/stream-groups').json()[0]['account_ids'] == [1, 2]


def test_snapshot_read_filters_stale_hidden_disabled_accounts_and_pages(database):
    apply(database)
    now = datetime.now(UTC)
    for index in range(6):
        artist = row(database, 'artists', slug=f'stream-{index}', entity_kind='solo', name_native=f'Singer {index}', show_in_catalog=index != 4)
        account = row(database, 'external_accounts', platform='youtube', platform_id='UC' + str(index) * 22,
                      url=f'https://youtube.com/channel/UC{str(index) * 22}', collection_enabled=index != 3)
        row(database, 'artist_external_accounts', artist_id=artist, account_id=account, relationship='owner')
        # Shared ownership must not duplicate a channel in the list.
        if index == 0:
            other = row(database, 'artists', slug='second-owner', entity_kind='solo', name_native='Other', show_in_catalog=True)
            row(database, 'artist_external_accounts', artist_id=other, account_id=account, relationship='member')
        checked = now - timedelta(minutes=20 if index == 2 else 1)
        snapshot = dict(checked_at=checked.isoformat(), streams=[dict(video_id=str(index)*11, title='Live', started_at=(now-timedelta(hours=index)).isoformat())])
        database.execute('INSERT INTO collection_states(external_account_id,provider_state) VALUES (%s,%s::jsonb)',
                         (account, json.dumps({'youtube_live_snapshot': snapshot})))
        if index == 5:
            database.execute('UPDATE external_accounts SET archived_at=clock_timestamp() WHERE id=%s', (account,))
    database.commit()
    info = database.info
    engine = create_engine(f'postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}')
    try:
        with Session(engine) as session:
            service = CatalogRead(session)
            result = service.live_streams(0, 1)
            assert result['total'] == 2
            assert result['items'][0]['artist_name'] == 'Singer 0'
            assert service.live_streams(1, 1)['items'][0]['artist_name'] == 'Singer 1'
            assert service.live_streams(2, 1)['total'] == 2
    finally:
        engine.dispose()
