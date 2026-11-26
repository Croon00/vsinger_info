"""Original-song world cup: the only browser write path, plus public statistics."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.catalog_session import CatalogIdentityError, catalog_runtime_session, get_catalog_session
from app.repositories import worldcup as repository
from app.schemas.worldcup import (VideoId, WorldcupPoolSummary, WorldcupStatsPage, WorldcupSubmission,
                                  WorldcupSubmitResult)
from app.services.worldcup import (CLIENT_RUNS_PER_HOUR, SubmissionRejected, address_limiter, check_pace,
                                   validate_bracket)
from app.services.worldcup_pool import pool_summary

SongKind = Literal['original', 'cover']

router = APIRouter(prefix='/worldcup', tags=['worldcup'], dependencies=[Depends(require_api_key)])
LOCAL_CLIENT = 'local-dev'  # set only by the local Vite proxy; such runs stay out of public stats


def write_session():
    try:
        with catalog_runtime_session() as session:
            yield session
    except CatalogIdentityError as exc:
        raise HTTPException(503, 'World cup storage is unavailable') from exc


def client_address(request: Request) -> str:
    forwarded = request.headers.get('x-forwarded-for', '')
    return forwarded.split(',')[0].strip() or (request.client.host if request.client else 'unknown')


def winner_stat(session, video_id, include_local, song_kind):
    items = repository.stats(session, include_local=include_local, song_kind=song_kind, video_ids=[video_id],
                             limit=1)['items']
    return items[0] if items else None


@router.post('/results', response_model=WorldcupSubmitResult, status_code=201)
def submit(submission: WorldcupSubmission, request: Request, response: Response,
           session: Annotated[Session, Depends(write_session)],
           x_utamowa_client: Annotated[str | None, Header()] = None):
    if not repository.ready(session):
        raise HTTPException(503, 'World cup storage is not ready')
    is_local = x_utamowa_client == LOCAL_CLIENT
    existing = repository.submission_run(session, submission.submission_id)
    if existing:  # retried submission: same answer, nothing stored twice
        response.status_code = 200
        return dict(run_id=existing.id, duplicate=True,
                    winner=winner_stat(session, submission.matches[-1].winner, existing.is_local, existing.song_kind))
    try:
        first_round, champion = validate_bracket(submission)
        check_pace(submission)
    except SubmissionRejected as exc:
        raise HTTPException(422, f'invalid_bracket:{exc}') from None
    if repository.playable_videos(session, first_round, submission.song_kind) != set(first_round):
        raise HTTPException(422, 'invalid_bracket:unknown_song')
    if (repository.recent_client_runs(session, submission.client_id) >= CLIENT_RUNS_PER_HOUR
            or not address_limiter.allow(client_address(request))):
        raise HTTPException(429, 'Too many world cup results; try again later')
    run_id = repository.insert_run(session, submission, champion, is_local)
    if run_id is None:
        existing = repository.submission_run(session, submission.submission_id)
        response.status_code = 200
        return dict(run_id=existing.id, duplicate=True,
                    winner=winner_stat(session, champion, existing.is_local, existing.song_kind))
    # Commit before answering: dependency teardown can run after the response is sent.
    session.commit()
    return dict(run_id=run_id, winner=winner_stat(session, champion, is_local, submission.song_kind))


@router.get('/stats', response_model=WorldcupStatsPage)
def stats(session: Annotated[Session, Depends(get_catalog_session)], response: Response,
          song_kind: SongKind = 'original',
          agency: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
          video_ids: Annotated[list[VideoId] | None, Query(max_length=128)] = None,
          order: Literal['championships', 'championship_rate', 'match_win_rate'] = 'championships',
          min_appearances: Annotated[int, Query(ge=1, le=10000)] = 1,
          offset: Annotated[int, Query(ge=0, le=100000)] = 0,
          limit: Annotated[int, Query(ge=1, le=100)] = 50,
          x_utamowa_client: Annotated[str | None, Header()] = None):
    if not repository.ready(session):
        raise HTTPException(503, 'World cup statistics are not ready')
    response.headers['Cache-Control'] = 'private, no-store'
    return repository.stats(session, include_local=x_utamowa_client == LOCAL_CLIENT, song_kind=song_kind,
                            agency=agency,
                            video_ids=sorted(set(video_ids or [])), order=order,
                            min_appearances=min_appearances, offset=offset, limit=limit)


@router.get('/pool-summary', response_model=WorldcupPoolSummary)
def pool(session: Annotated[Session, Depends(get_catalog_session)], response: Response,
         song_kind: SongKind = 'original'):
    """Playable songs per agency and artist (read-only, cached for a few minutes)."""
    response.headers['Cache-Control'] = 'private, max-age=300'
    return pool_summary(session, song_kind)
