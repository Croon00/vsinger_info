from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_artist_service
from app.core.security import require_api_key
from app.repositories.errors import ConflictError, NotFoundError
from app.schemas.artists import Artist, ArtistAgency, ArtistAgencyCreate, ArtistCreate, ArtistUpdate, ArtistWithSources, EventCandidate, EventCandidateCreate, Source, SourceCreate
from app.services.artist_service import ArtistService

router = APIRouter(tags=["artists"], dependencies=[Depends(require_api_key)])
Service = Annotated[ArtistService, Depends(get_artist_service)]


def _raise_http(error: Exception) -> None:
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise error


@router.get("/artist-agencies", response_model=list[ArtistAgency])
def list_artist_agencies(service: Service) -> list[ArtistAgency]:
    return service.list_agencies()


@router.post("/artist-agencies", response_model=ArtistAgency, status_code=status.HTTP_201_CREATED)
def create_artist_agency(payload: ArtistAgencyCreate, service: Service) -> ArtistAgency:
    try:
        return service.create_agency(payload.name)
    except ConflictError as exc:
        _raise_http(exc)


@router.post("/artists", response_model=ArtistWithSources, status_code=status.HTTP_201_CREATED)
def create_artist(payload: ArtistCreate, service: Service) -> dict:
    return service.create_artist(payload)


@router.get("/artists", response_model=list[ArtistWithSources])
def list_artists(service: Service, grouped: bool = False) -> list[dict]:
    return service.list_artists(grouped=grouped)


@router.get("/artists/{artist_id}", response_model=ArtistWithSources)
def get_artist(artist_id: int, service: Service) -> dict:
    try:
        return service.get_artist(artist_id)
    except NotFoundError as exc:
        _raise_http(exc)


@router.patch("/artists/{artist_id}", response_model=Artist)
def update_artist(artist_id: int, payload: ArtistUpdate, service: Service) -> dict:
    try:
        return service.update_artist(artist_id, payload)
    except NotFoundError as exc:
        _raise_http(exc)


@router.delete("/artists/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artist(artist_id: int, service: Service) -> Response:
    try:
        service.delete_artist(artist_id)
    except NotFoundError as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/artists/{artist_id}/sources", response_model=Source, status_code=status.HTTP_201_CREATED)
def add_artist_source(artist_id: int, payload: SourceCreate, service: Service) -> dict:
    try:
        return service.add_source(artist_id, payload)
    except (NotFoundError, ConflictError) as exc:
        _raise_http(exc)


@router.get("/artists/{artist_id}/sources", response_model=list[Source])
def list_artist_sources(artist_id: int, service: Service) -> list[dict]:
    try:
        return service.list_sources(artist_id)
    except NotFoundError as exc:
        _raise_http(exc)


@router.delete("/artists/{artist_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artist_source(artist_id: int, source_id: int, service: Service) -> Response:
    try:
        service.delete_source(artist_id, source_id)
    except NotFoundError as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/event-candidates", response_model=EventCandidate, status_code=status.HTTP_201_CREATED)
def create_event_candidate(payload: EventCandidateCreate, service: Service) -> EventCandidate:
    return service.create_event_candidate(payload)


@router.get("/event-candidates", response_model=list[EventCandidate])
def list_event_candidates(service: Service, status_filter: str | None = None, artist_id: int | None = None, event_type: str | None = None, event_format: str | None = None) -> list[EventCandidate]:
    return service.list_event_candidates(status=status_filter, artist_id=artist_id, event_type=event_type, event_format=event_format)
