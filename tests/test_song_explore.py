import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api.routers.read_api import router, catalog
from app.core.config import settings
from app.integrations.youtube_video_statistics import fetch_statistics
from app.integrations.youtube_video_statistics import VideoStatistics
from app.repositories.youtube_video_statistics import persist
from test_catalog_migration import local_server, database, row
from test_new_catalog_read import store, seed
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.repositories.song_explore import explore, performers


def test_view_counts_preserve_unknown_zero_and_validate_identity():
    provider = AsyncMock()
    provider.get.return_value = {'items': [
        dict(id='abcdefghijk', snippet={'channelId': 'UC'+'a'*22}, statistics={'viewCount': '121000'}),
        dict(id='abcdefghij0', snippet={'channelId': 'UC'+'a'*22}, statistics={'viewCount': '0'}),
        dict(id='abcdefghij1', snippet={'channelId': 'UC'+'a'*22}, statistics={}),
    ]}
    rows = asyncio.run(fetch_statistics(provider, ['abcdefghijk','abcdefghij0','abcdefghij1'], datetime.now(UTC)))
    assert [r.view_count for r in rows] == [121000, 0, None]
    with pytest.raises(ValueError):
        asyncio.run(fetch_statistics(provider, ['abcdefghij2'], datetime.now(UTC)))


def test_song_endpoint_contract_auth_and_input_validation(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix='/api')
    calls = []
    def explore(**kwargs):
        calls.append(kwargs)
        return dict(items=[],total=0,offset=kwargs['offset'],limit=kwargs['limit'])
    app.dependency_overrides[catalog] = lambda: SimpleNamespace(query_ms=0,query_count=0,explore_songs=explore,
        song_performers=lambda key,agency: [dict(id=1,name='Singer',display_name=None)])
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app) as client:
        assert client.get('/api/explore/songs').status_code == 401
        client.headers['X-API-Key'] = 'fixture'
        assert client.get('/api/explore/song-performers?song_key=song:1').json()[0]['id']==1
        assert client.get('/api/explore/song-performers?song_key=bad').status_code==422
        for kind in ['utawaku','cover','original']:
            response = client.get('/api/explore/songs',params=dict(kind=kind,agency='Group',q=' Song ',order='low',offset=24,limit=24))
            assert response.status_code == 200, response.text
            assert response.json()['offset'] == 24
            assert calls[-1]['q'] == 'Song' and calls[-1]['agency'] == 'Group'
        for query in ['kind=bad','order=bad','limit=0','limit=101','offset=-1']:
            assert client.get('/api/explore/songs?'+query).status_code == 422
        assert client.get('/api/explore/songs?kind=cover&artist_ids=2&artist_ids=1&artist_ids=2').status_code==200
        assert calls[-1]['artist_ids']==[1,2]
        assert client.get('/api/explore/songs?kind=utawaku&artist_ids=1&artist_ids=2').status_code==200
        assert calls[-1]['artist_ids']==[1,2]
        for query in ['kind=cover&artist_ids=0','kind=original&artist_ids=bad','kind=utawaku&artist_ids=-1']:
            assert client.get('/api/explore/songs?'+query).status_code==422
        assert client.get('/api/explore/songs?kind=cover&start=2026-10-01&end=2026-10-31').status_code==200
        assert str(calls[-1]['start'])=='2026-10-01' and str(calls[-1]['end'])=='2026-10-31'
        for query in ['kind=cover&start=bad','kind=original&start=2026-10-31&end=2026-10-01','kind=utawaku&start=2026-10-01']:
            assert client.get('/api/explore/songs?'+query).status_code==422


def test_view_batches_keep_previous_video_counts_and_other_namespaces(store):
    db, engine = store
    artist, *_ = seed(db)
    account = db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s', (artist,)).fetchone()[0]
    db.execute('UPDATE external_accounts SET platform_id=%s WHERE id=%s', ('UC'+'a'*22, account))
    db.commit()
    with Session(engine) as session:
        session.execute(text("INSERT INTO collection_states(external_account_id,provider_state) VALUES (:id,CAST(:state AS jsonb))"),
            {'id': account, 'state': json.dumps({'youtube_channel_statistics': {'subscriber_count': 123}})})
        first = VideoStatistics(video_id='abcdefghijk',channel_id='UC'+'a'*22,view_count=10,captured_at=datetime.now(UTC))
        second = first.model_copy(update={'video_id':'abcdefghij0','view_count':20})
        persist(session, account, [first])
        persist(session, account, [second])
        session.commit()
        state = session.execute(text('SELECT provider_state FROM collection_states WHERE external_account_id=:id'), {'id':account}).scalar_one()
        assert state['youtube_channel_statistics']['subscriber_count'] == 123
        assert state['youtube_video_statistics']['abcdefghijk']['view_count'] == 10
        assert state['youtube_video_statistics']['abcdefghij0']['view_count'] == 20


def test_song_explore_excludes_unknown_originals_and_shorts_and_finds_singers(store):
    db, engine = store
    artist, guest, original, archive, *_ = seed(db)
    row(db, 'performances', archive_id=archive,ordinal=3,start_seconds=150,raw_title='No original')
    account = db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s',(artist,)).fetchone()[0]
    for index, (title,duration) in enumerate([('Normal cover',240),('Song #shorts',30),('Short normal cover',120)]):
        video=row(db,'videos',platform='youtube',platform_video_id=f'clip{index:07}',title=title,duration_seconds=duration,source_account_id=account)
        row(db,'covers',video_id=video)
    db.commit()
    with Session(engine) as session:
        page=explore(session,kind='utawaku',agency='all',q='Singer',order='high',offset=0,limit=24)
        assert page['total']==1 and page['items'][0]['performance_count']==2
        assert page['items'][0]['artist_name']=='Original'
        from app.repositories.catalog_read import CatalogReadRepository
        assert {r['id'] for r in performers(CatalogReadRepository(session),page['items'][0]['key'],'all')} == {artist,guest}
        covers=explore(session,kind='cover',agency='all',q='Singer',order='high',offset=0,limit=24)
        assert [r['title'] for r in covers['items']]==['Normal cover']


def test_original_recording_is_not_hidden_by_old_description_only_cover(store):
    db,engine=store
    artist,guest,original,archive,concert,album,recording=seed(db)
    account=db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s',(artist,)).fetchone()[0]
    video=row(db,'videos',platform='youtube',platform_video_id='originalMV1',title='Original Music Video',source_account_id=account,duration_seconds=240)
    row(db,'covers',video_id=video)
    db.execute('UPDATE recordings SET official_video_id=%s WHERE id=%s',(video,recording));db.commit()
    with Session(engine) as session:
        assert explore(session,kind='cover',agency='all',q='',order='high',offset=0,limit=24)['total']==0
        page=explore(session,kind='original',agency='all',q='',order='high',offset=0,limit=24)
        assert page['total']==1 and page['items'][0]['youtube_video_id']=='originalMV1'


def test_originals_deduplicate_same_video_before_pagination_but_keep_other_videos(store):
    db,engine=store
    artist,guest,original,archive,concert,album,recording=seed(db)
    video=row(db,'videos',platform='youtube',platform_video_id='sameVideo01',title='Official MV')
    other=row(db,'videos',platform='youtube',platform_video_id='otherVideo1',title='Another version')
    db.execute('UPDATE recordings SET official_video_id=%s WHERE id=%s',(video,recording))
    for title,video_id in [('Album title',video),('Another version',other),('No video',None)]:
        duplicate=row(db,'recordings',title_native=title,official_video_id=video_id)
        row(db,'recording_artists',recording_id=duplicate,artist_id=artist,role='primary')
    db.commit()
    with Session(engine) as session:
        page=explore(session,kind='original',agency='all',q='',order='high',offset=0,limit=1)
        assert page['total']==3
        pages=[explore(session,kind='original',agency='all',q='',order='high',offset=i,limit=1) for i in range(3)]
        ids=[p['items'][0]['youtube_video_id'] for p in pages]
        assert len(ids)==len(set(ids))==3
        alternate=explore(session,kind='original',agency='all',q='Album title',order='high',offset=0,limit=24)
        assert alternate['total']==1 and alternate['items'][0]['youtube_video_id']=='sameVideo01'


def test_artist_union_keeps_collaborator_names_and_scopes_before_pagination(store):
    db,engine=store
    artist,guest,original,archive,concert,album,recording=seed(db)
    account=db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s',(artist,)).fetchone()[0]
    row(db,'artist_external_accounts',artist_id=guest,account_id=account,relationship='owner')
    guest_account=row(db,'external_accounts',platform='youtube',url='https://youtube.com/@guest')
    row(db,'artist_external_accounts',artist_id=guest,account_id=guest_account,relationship='owner')
    for n,source in enumerate([account,guest_account]):
        video=row(db,'videos',platform='youtube',platform_video_id=f'coverunion{n}',title=f'Song {n} cover',duration_seconds=240,source_account_id=source)
        row(db,'covers',video_id=video)
    row(db,'recording_artists',recording_id=recording,artist_id=guest,role='featured')
    second=row(db,'recordings',title_native='Guest song')
    row(db,'recording_artists',recording_id=second,artist_id=guest,role='primary')
    db.commit()
    with Session(engine) as s:
        for kind in ['cover','original']:
            def page(ids,offset=0,agency='all'):
                return explore(s,kind=kind,agency=agency,q='',order='high',offset=offset,limit=1,artist_ids=ids)
            assert page([])['total']==2
            assert page([artist])['total']==1
            assert page([guest])['total']==2
            assert page([artist,guest])['total']==2
            assert page([artist,guest],1)['total']==2
            assert page([original])['total']==0
            assert page([artist],agency='Other agency')['total']==0
            assert 'Singer' in page([artist])['items'][0]['artist_name']
            assert 'Guest' in page([artist])['items'][0]['artist_name']


def test_utawaku_selection_counts_only_selected_singers_without_duplicate_duets(store):
    db,engine=store
    artist,guest,original,archive,*_=seed(db)
    perf=db.execute('SELECT id FROM performances WHERE archive_id=%s AND ordinal=1',(archive,)).fetchone()[0]
    row(db,'performance_artists',performance_id=perf,artist_id=guest,role='guest')
    db.commit()
    with Session(engine) as s:
        def page(ids):return explore(s,kind='utawaku',agency='all',q='',order='high',offset=0,limit=24,artist_ids=ids)
        one=page([artist])
        assert one['total']==1 and one['items'][0]['performance_count']==1 and one['items'][0]['artist_count']==1
        assert page([guest])['items'][0]['performance_count']==2
        both=page([artist,guest])
        assert both['total']==1 and both['items'][0]['performance_count']==2 and both['items'][0]['artist_count']==2
        assert page([original])['total']==0


def test_song_publication_range_includes_both_korean_calendar_dates_before_paging(store):
    from datetime import date
    db,engine=store
    artist,*_=seed(db)
    account=db.execute('SELECT account_id FROM artist_external_accounts WHERE artist_id=%s',(artist,)).fetchone()[0]
    for kind,prefix in [('cover','datecover'),('original','dateorigi')]:
        for n,stamp in enumerate(['2026-10-01T15:00:00Z','2026-10-02T15:00:00Z']):
            video=row(db,'videos',platform='youtube',platform_video_id=f'{prefix}{n:02}',title='Song cover' if kind=='cover' else 'Official MV',published_at=stamp,duration_seconds=240,source_account_id=account)
            if kind=='cover':row(db,'covers',video_id=video)
            else:
                recording=row(db,'recordings',title_native=f'Dated {n}',official_video_id=video)
                row(db,'recording_artists',recording_id=recording,artist_id=artist,role='primary')
    db.commit()
    with Session(engine) as s:
        for kind in ['cover','original']:
            kwargs=dict(kind=kind,agency='all',q='',order='high',artist_ids=[artist],start=date(2026,10,2),end=date(2026,10,2))
            page=explore(s,offset=0,limit=1,**kwargs)
            assert page['total']==1 and page['items'][0]['youtube_video_id'].endswith('00')
            assert explore(s,offset=9,limit=1,**kwargs)['total']==1
            kwargs['end']=date(2026,10,3)
            assert explore(s,offset=0,limit=1,**kwargs)['total']==2
