from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routers.read_api import catalog, router
from app.core.config import settings
from app.repositories.catalog_read import CatalogReadRepository
from test_catalog_migration import local_server, database, row
from test_new_catalog_read import store, seed


def test_search_multi_artist_dates_and_facet_contract(monkeypatch):
    app=FastAPI();app.include_router(router,prefix='/api')
    calls=[]
    def search(*args,**kwargs):
        calls.append((args,kwargs))
        return {'items':[],'total':0,'offset':args[1],'limit':args[2]}
    app.dependency_overrides[catalog]=lambda:SimpleNamespace(query_ms=0,query_count=0,search=search,
        search_performers=lambda q,agency,artist:[{'id':7,'name':'Singer','display_name':None}])
    monkeypatch.setattr(settings,'api_key','fixture')
    with TestClient(app) as c:
        assert c.get('/api/search/performers?q=Song').status_code==401
        c.headers['X-API-Key']='fixture'
        r=c.get('/api/search?q=Song&artist_ids=7&artist_ids=9&artist_ids=7&start=2026-10-01&end=2026-10-31')
        assert r.status_code==200
        assert calls[-1][1]=={'artist_ids':[7,9],'start':date(2026,10,1),'end':date(2026,10,31)}
        assert c.get('/api/search/performers?q=Song').json()[0]['id']==7
        for query in ['artist_ids=0','artist_ids=-1','artist_ids=bad','start=bad','start=2026-10-31&end=2026-10-01']:
            assert c.get('/api/search?q=Song&'+query).status_code==422
        assert c.get('/api/search?q=Song&'+'&'.join('artist_ids=1' for _ in range(101))).status_code==422


def test_union_is_deduplicated_before_pagination_and_dates_include_korean_day(store):
    db,engine=store
    artist,guest,_,archive,*_=seed(db)
    # A duet matches either selected singer but is still one performance.
    perf=db.execute('SELECT id FROM performances WHERE archive_id=%s AND ordinal=1',(archive,)).fetchone()[0]
    row(db,'performance_artists',performance_id=perf,artist_id=guest,role='guest')
    db.execute("UPDATE live_archives SET broadcast_at='2026-10-01T15:00:00Z' WHERE id=%s",(archive,))
    db.commit()
    with Session(engine) as s:
        repo=CatalogReadRepository(s)
        page=repo.search('Title',0,1,artist_ids=[artist,guest],start=date(2026,10,2),end=date(2026,10,2))
        assert page['total']==2 and len(page['items'])==1
        assert repo.search('Title',1,1,artist_ids=[artist,guest],start=date(2026,10,2),end=date(2026,10,2))['total']==2
        assert repo.search('Title',0,50,artist_ids=[guest])['items'][0]['artist_id']==guest
        assert repo.search('Title',0,50,end=date(2026,10,1))['total']==0
        assert {a['id'] for a in repo.search_performers('Title')}=={artist,guest}
