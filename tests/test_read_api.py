"""Read API regression tests without a database or external services."""
import asyncio
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routers.read_api import router, catalog
from app.core.config import settings
from app.services.read_catalog import ReadCatalog
from app.services.read_spotify import ReadCache
from app.db import session as sessions

def test_catalog_has_constant_query_count_and_preserves_representative_ids():
    service=ReadCatalog(None)
    service.rows=Mock(side_effect=[
      [{'id':i,'name':f'Artist {i}','display_name':None,'agency':None,'spotify_image_url':None,'profile_intro':None} for i in range(1,101)], []])
    assert len(service.artists())==100
    assert service.artist(50)['id']==50
    assert service.rows.call_count==2

def test_source_less_identity_is_exact_and_ambiguous_names_are_excluded():
    service=ReadCatalog(None)
    service._artists=[{'id':1,'name':'HACHI','display_name':'HACHI','name_aliases':['ハチ'],'related_artist_ids':[1,4]},
                      {'id':2,'name':'Other','display_name':'Other','name_aliases':['ハチ'],'related_artist_ids':[2]}]
    sql,params=service.scope(4)
    assert params=={'ids':[1,4],'aliases':['hachi']}
    assert 's.id IS NULL' in sql and 'ILIKE' not in sql

def test_paged_search_is_or_literal_and_deterministic():
    service=ReadCatalog(None)
    service.rows=Mock(return_value=[{'id':7,'_total':81}])
    page=service.search('a%_',50,50)
    sql,params=service.rows.call_args.args
    assert page=={'items':[{'id':7}],'total':81,'offset':50,'limit':50}
    assert params['q']==r'%a\%\_%'
    assert 'OR p.original_artist' in sql
    assert 'ORDER BY q.performed_on' in sql

def test_detail_queries_only_stored_data():
    service=ReadCatalog(None)
    service.rows=Mock(side_effect=[[{'id':1}], [{'id':2}]])
    assert service.live(1)=={'id':1,'performances':[{'id':2}]}
    assert all(call.args[0].lstrip().startswith('SELECT') for call in service.rows.call_args_list)

def test_statistics_include_empty_archives_unknown_artists_and_tied_rank():
    service=ReadCatalog(None)
    service.scope=Mock(return_value=('TRUE',{}))
    service.rows=Mock(side_effect=[
      [{'song_key':'a','artist_key':'band','title':'A','artist':'Band','count':2,'last_date':None,'search':'A Band'},
       {'song_key':'b','artist_key':'','title':'B','artist':'','count':2,'last_date':None,'search':'B'}],
      [{'total':3,'with_setlist':2,'month_key':'2026-09','activity_count':3}]])
    result=service.statistics(1)
    assert result.archives==3 and result.archivesWithSetlist==2
    assert result.performances==4 and result.uniqueSongs==2 and result.uniqueArtists==1
    assert [s.rank for s in result.songs]==[1,1]
    assert result.artists[0].percentage==50

def test_engine_is_reused_but_database_url_changes_are_respected(monkeypatch):
    sessions._engine_for_url.cache_clear()
    factory=Mock(side_effect=[object(),object()])
    monkeypatch.setattr(sessions,'create_engine',factory)
    monkeypatch.setattr(settings,'database_url','postgresql://test/db1')
    assert sessions.get_engine() is sessions.get_engine()
    monkeypatch.setattr(settings,'database_url','postgresql://test/db2')
    sessions.get_engine()
    assert factory.call_count==2
    sessions._engine_for_url.cache_clear()

def test_cache_coalesces_and_does_not_cache_errors():
    async def scenario():
        cache=ReadCache()
        calls=[]
        async def loader():
            calls.append(1)
            await asyncio.sleep(0)
            return 42
        assert await asyncio.gather(cache.get('x',loader),cache.get('x',loader))==[42,42]
        assert await cache.get('x',loader)==42
        assert len(calls)==1
        async def failure():
            raise ValueError('failed')
        with pytest.raises(ValueError):
            await cache.get('y',failure)
        assert await cache.get('y',loader)==42
    asyncio.run(scenario())

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings,'api_key','test-key')
    app=FastAPI()
    app.include_router(router,prefix='/api')
    service=Mock(query_ms=1.0,query_count=2)
    service.artists.return_value=[]
    service.artist.return_value=None
    service.live.return_value=None
    app.dependency_overrides[catalog]=lambda:service
    with TestClient(app) as client:
        yield client

def test_read_contract_auth_validation_and_missing_resources(client):
    assert client.get('/api/v2/artists').status_code==401
    headers={'X-API-Key':'test-key'}
    result=client.get('/api/v2/artists',headers=headers)
    assert result.json()==[] and 'queries' in result.headers['server-timing']
    assert client.get('/api/v2/artists/1',headers=headers).status_code==404
    assert client.get('/api/v2/lives/1',headers=headers).status_code==404
    assert client.get('/api/v2/search?q=test&limit=101',headers=headers).status_code==422
    assert client.get('/api/v2/search?q=test&offset=-1',headers=headers).status_code==422
    assert client.get('/api/v2/concerts?start=2026-10-01&end=2026-09-01',headers=headers).status_code==422
    assert client.post('/api/v2/artists',headers=headers).status_code==405
