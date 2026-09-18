"""Frontend read API. Existing /api endpoints remain compatible."""
from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.core.security import require_api_key
from app.db.session import get_session
from app.services.read_catalog import ReadCatalog
from app.services import read_spotify
from app.schemas.read_models import ArtistRead, LiveRead, SearchRead, Page, StatisticsRead, ConcertRead
from app.integrations.spotify import SpotifyAlbumSummary, SpotifyAlbumDetail, spotify_configured

router = APIRouter(prefix='/v2',tags=['frontend-read'],dependencies=[Depends(require_api_key)])
def catalog(response: Response, session: Annotated[Session, Depends(get_session)]):
    service = ReadCatalog(session)
    yield service
    # Headers assigned before return in finish(); yield teardown is too late.

Catalog = Annotated[ReadCatalog, Depends(catalog)]
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

@router.get('/spotify/artists/{artist_id}/discography',response_model=list[SpotifyAlbumSummary])
async def discography(artist_id:int,service:Catalog,response:Response):
    def resolve():
        require_artist(service,artist_id)
        ids=service.artist(artist_id)['related_artist_ids']
        return service.rows('SELECT spotify_artist_id FROM artists WHERE id=ANY(:ids) AND spotify_artist_id IS NOT NULL ORDER BY id LIMIT 1',{'ids':ids})
    rows=await run_in_threadpool(resolve)
    if not rows:
        raise HTTPException(409,'Spotify artist not linked')
    if not spotify_configured():
        raise HTTPException(503,'Spotify unavailable')
    # Release the database connection before waiting for an external service.
    await run_in_threadpool(service.session.rollback)
    try:
        value=await read_spotify.discography(rows[0]['spotify_artist_id'])
    except Exception as exc:
        raise HTTPException(502,'Spotify read failed') from exc
    return finish(response,service,value)

@router.get('/spotify/albums/{album_id}',response_model=SpotifyAlbumDetail)
async def album(album_id:str,service:Catalog,response:Response):
    if not spotify_configured():
        raise HTTPException(503,'Spotify unavailable')
    try:
        value=await read_spotify.album(album_id)
    except Exception as exc:
        raise HTTPException(502,'Spotify read failed') from exc
    # Apply only already-stored translations; no LLM or INSERT/UPDATE in GET.
    ids=[t.id for t in value.tracks]
    rows=await run_in_threadpool(service.rows,'SELECT spotify_track_id,title_ko FROM spotify_track_title_translations WHERE spotify_track_id=ANY(:ids)',{'ids':ids}) if ids else []
    translations={r['spotify_track_id']:r['title_ko'] for r in rows}
    return finish(response,service,value.model_copy(update={'tracks':[t.model_copy(update={'name_ko':translations.get(t.id)}) for t in value.tracks]}))

@router.get('/concerts/{event_id}',response_model=ConcertRead)
def concert(event_id:int,service:Catalog,response:Response):
    value=service.concert(event_id)
    if value is None:
        raise HTTPException(404,'Concert not found')
    return finish(response,service,value)
