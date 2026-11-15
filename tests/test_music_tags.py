import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.routers.read_api import router, catalog
from app.core.config import settings
from app.schemas.music_tags import MusicTagCatalog, OriginalMusicTags
from scripts.collect_original_music_tags import ProposedVideo, verified_tags
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_catalog_migration import local_server, database, row
from test_new_catalog_read import store, seed
from app.repositories.song_explore import explore


def test_published_catalog_requires_exact_identity_and_evidence():
    data = json.loads(Path('data/classification/original_music_tags.json').read_text(encoding='utf8'))
    parsed = MusicTagCatalog.model_validate(data)
    assert parsed.items
    good = parsed.items[0].model_dump(mode='json')
    for mutation in [dict(genres=['unknown']), dict(sources=[]), dict(youtube_video_id=None, recording_key=None),
                     dict(genres=['acoustic'], sources=good['sources'])]:
        with pytest.raises(ValidationError):
            OriginalMusicTags.model_validate({**good, **mutation})
    with pytest.raises(ValidationError):
        MusicTagCatalog.model_validate({**data, 'items': [good, good]})


def test_proposals_cannot_publish_fabricated_quotes_or_wrong_dimension():
    result = verified_tags({'id': 'abcdefghijk'}, ProposedVideo(candidate_id='c0', tags=[
        dict(dimension='genre', tag='rock', quote='not in source'),
        dict(dimension='mood', tag='rock', quote='rock ballad'),
        dict(dimension='genre', tag='ballad', quote='rock ballad'),
    ]), 'This version is a rock ballad')
    assert result['genres'] == ['ballad'] and result['moods'] == []


def test_music_filter_contract(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix='/api')
    calls = []
    def explore(**kwargs):
        calls.append(kwargs)
        return dict(items=[], total=0, offset=0, limit=24)
    app.dependency_overrides[catalog] = lambda: SimpleNamespace(query_ms=0, query_count=0, explore_songs=explore)
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app) as client:
        assert client.get('/api/explore/music-tags').status_code == 401
        client.headers['X-API-Key'] = 'fixture'
        options = client.get('/api/explore/music-tags')
        assert options.status_code == 200
        assert 'jpop' not in [r['value'] for r in options.json()['genres']]
        assert client.get('/api/explore/songs?kind=original&genres=rock&genres=ballad&genres=rock&moods=calm').status_code == 200
        assert calls[-1]['genres'] == ['ballad', 'rock'] and calls[-1]['moods'] == ['calm']
        for query in ['kind=cover&genres=rock', 'kind=original&moods=rock', 'kind=original&genres=jpop']:
            assert client.get('/api/explore/songs?' + query).status_code == 422


def test_filters_before_paging_and_recording_identity_guards(store):
    db, engine = store
    artist, *_, recording = seed(db)
    extra = row(db, 'recordings', title_native='Other')
    row(db, 'recording_artists', recording_id=extra, artist_id=artist, role='primary')
    db.commit()
    tag = dict(recording_key=f'recording:{recording}', recording_title='Title', recording_artist='Singer',
               genres=['rock', 'ballad'], moods=['calm'], sources=[])
    args = dict(kind='original', agency='all', q='', order='name', limit=1, music_tags=[tag])
    with Session(engine) as session:
        page = explore(session, **args, offset=0, genres=['rock', 'jazz'], moods=['calm'])
        assert page['total'] == 1 and page['items'][0]['key'] == f'recording:{recording}'
        page = explore(session, **args, offset=3, genres=['rock'], moods=['calm'])
        assert page['total'] == 1 and page['items'] == []
        assert explore(session, **args, offset=0, genres=['rock'], moods=['upbeat'])['total'] == 0
        args['music_tags'] = [{**tag, 'recording_artist': 'Wrong Artist'}]
        assert explore(session, **args, offset=0, genres=['rock'])['total'] == 0
