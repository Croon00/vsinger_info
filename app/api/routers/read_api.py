"""Canonical unified-DB read API mounted at ``/api``."""
from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.core.security import require_api_key
from app.db.catalog_session import get_catalog_session
from app.services.catalog_read import CatalogRead
from app.schemas.read_models import ArtistRead, LiveRead, SearchRead, Page, StatisticsRead, ConcertRead
from app.schemas.read_models import CatalogAlbumRead, CatalogLyricsRead

router = APIRouter(tags=['frontend-read'],dependencies=[Depends(require_api_key)])
def catalog(response: Response, session: Annotated[Session, Depends(get_catalog_session)]):
    service = CatalogRead(session)
    yield service
    # Headers assigned before return in finish(); yield teardown is too late.

Catalog = Annotated[CatalogRead, Depends(catalog)]
Offset = Annotated[int, Query(ge=0,le=100000)]
Limit = Annotated[int, Query(ge=1,le=100)]

def finish(response, service, value):
    response.headers['Server-Timing'] = f'db;dur={service.query_ms:.1f}, queries;desc="{service.query_count}"'
    response.headers['Cache-Control'] = 'private, no-store'
    return value

def require_artist(service, artist_id):
    if not service.artist(artist_id):
        raise HTTPException(404,'Artist not found')

@router.get('/artists',response_model=list[ArtistRead])
def artists(service: Catalog,response: Response):
    return finish(response,service,service.artists())

@router.get('/artists/{artist_id}',response_model=ArtistRead)
def artist(artist_id:int,service:Catalog,response:Response):
    require_artist(service,artist_id)
    return finish(response,service,service.artist(artist_id))

@router.get('/artists/{artist_id}/lives',response_model=Page[LiveRead])
def lives(artist_id:int,service:Catalog,response:Response,offset:Offset=0,limit:Limit=12):
    require_artist(service,artist_id)
    return finish(response,service,service.lives(artist_id,offset,limit))

@router.get('/lives/{archive_id}',response_model=LiveRead)
def live(archive_id:int,service:Catalog,response:Response):
    value=service.live(archive_id)
    if value is None:
        raise HTTPException(404,'Archive not found')
    return finish(response,service,value)

@router.get('/artists/{artist_id}/statistics',response_model=StatisticsRead)
def statistics(artist_id:int,service:Catalog,response:Response):
    require_artist(service,artist_id)
    return finish(response,service,service.statistics(artist_id))

@router.get('/search',response_model=Page[SearchRead])
def search(service:Catalog,response:Response,q:Annotated[str,Query(min_length=1,max_length=200)],offset:Offset=0,limit:Limit=50):
    return finish(response,service,service.search(q.strip(),offset,limit) if q.strip() else {'items':[],'total':0,'offset':offset,'limit':limit})

@router.get('/concerts',response_model=Page[ConcertRead])
def concerts(service:Catalog,response:Response,offset:Offset=0,limit:Limit=100,artist_id:int|None=None,start:date|None=None,end:date|None=None):
    if start and end and start>=end:
        raise HTTPException(422,'end must be after start')
    if artist_id is not None:
        require_artist(service,artist_id)
    return finish(response,service,service.concerts(offset,limit,artist_id,start,end))

@router.get('/artists/{artist_id}/albums',response_model=list[CatalogAlbumRead])
def discography(artist_id:int,service:Catalog,response:Response):
    require_artist(service,artist_id)
    return finish(response,service,service.albums(artist_id))

@router.get('/albums/{album_id}',response_model=CatalogAlbumRead)
def album(album_id:int,service:Catalog,response:Response):
    value=service.album(album_id)
    if value is None:
        raise HTTPException(404,'Album not found')
    return finish(response,service,value)

@router.get('/recordings/{recording_id}/lyrics',response_model=CatalogLyricsRead)
def lyrics(recording_id:int,service:Catalog,response:Response):
    value=service.lyrics(recording_id)
    if value is None:
        raise HTTPException(404,'Lyrics not found')
    return finish(response,service,value)

@router.get('/concerts/{event_id}',response_model=ConcertRead)
def concert(event_id:int,service:Catalog,response:Response):
    value=service.concert(event_id)
    if value is None:
        raise HTTPException(404,'Concert not found')
    return finish(response,service,value)
