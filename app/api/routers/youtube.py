"""YouTube 라이브·공연 API 라우터다."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_youtube_service
from app.core.models import YouTubePerformanceUpdate
from app.core.security import require_api_key
from app.schemas.youtube import YouTubeChannelBackfillCreate, YouTubeCoverVideo, YouTubeLiveCreate
from app.services.youtube_service import YouTubeService

router = APIRouter(tags=["youtube"], dependencies=[Depends(require_api_key)])
Service = Annotated[YouTubeService, Depends(get_youtube_service)]
_backfill_tasks: set[asyncio.Task] = set()


@router.post("/youtube-lives", status_code=status.HTTP_201_CREATED)
async def create_youtube_live(payload: YouTubeLiveCreate, service: Service) -> dict:
    """YouTube 라이브를 등록한다."""
    try:
        archive = await service.create_live(str(payload.youtube_url), payload.artist_name)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="YouTube 정보를 가져오지 못했습니다.") from exc
    if archive is None:
        raise HTTPException(status_code=404, detail="YouTube 라이브 기록을 찾지 못했습니다.")
    return archive


@router.post("/youtube-lives/backfills", status_code=status.HTTP_202_ACCEPTED)
async def create_youtube_live_backfill(payload: YouTubeChannelBackfillCreate, service: Service) -> dict[str, str]:
    """채널 과거 라이브 수집 작업을 백그라운드로 시작한다."""
    task = asyncio.create_task(service.backfill_channel(str(payload.channel_url), payload.artist_name))
    _backfill_tasks.add(task)
    task.add_done_callback(_backfill_tasks.discard)
    return {"status": "accepted"}


@router.get("/youtube-lives")
def get_youtube_lives(service: Service, limit: int = 50, artist_name: str | None = None, all_records: bool = False) -> list[dict]:
    """저장된 YouTube 라이브를 조회한다."""
    return service.list_lives(limit, artist_name, all_records=all_records)


@router.get("/youtube-covers", response_model=list[YouTubeCoverVideo])
def get_youtube_covers(service: Service, artist_id: int | None = None, collaborator_id: int | None = None, limit: int = 500) -> list[dict]:
    """Return cover uploads collected from registered artists' official channels."""
    return service.list_covers(artist_id=artist_id, collaborator_id=collaborator_id, limit=limit)


@router.get("/youtube-lives/{archive_id}")
async def get_youtube_live(archive_id: int, service: Service) -> dict:
    """YouTube 라이브 상세 정보를 조회한다."""
    archive = await service.get_live(archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="YouTube 라이브 기록을 찾지 못했습니다.")
    return archive


@router.get("/youtube-performances")
def search_youtube_performances(service: Service, artist_name: list[str] = Query(default=[]), song_title: list[str] = Query(default=[]), original_artist: list[str] = Query(default=[]), limit: int = 200) -> list[dict]:
    """YouTube 공연 곡을 조건으로 검색한다."""
    try:
        return service.search_performances(artist_names=artist_name, song_titles=song_title, original_artists=original_artist, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/youtube-performance-filters")
def get_youtube_performance_filters(service: Service) -> dict[str, list[str]]:
    """공연 검색 필터를 조회한다."""
    return service.list_performance_filters()


@router.get("/youtube-performance-stats")
def get_youtube_performance_stats(service: Service, group_by: str = "song") -> list[dict]:
    if group_by not in {"song", "original_artist"}:
        raise HTTPException(status_code=400, detail="group_by must be song or original_artist")
    return service.list_performance_stats(group_by)


@router.patch("/youtube-performances/{performance_id}")
def patch_youtube_performance(performance_id: int, payload: YouTubePerformanceUpdate, service: Service) -> dict:
    """공연 곡 정보를 수정한다."""
    try:
        updated = service.update_performance(performance_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="공연 기록을 찾지 못했습니다.")
    return updated
