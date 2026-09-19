from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, HttpUrl
from psycopg import Connection, errors

from app.core.config import settings
from app.core.artist_identity import group_artists
from app.core.db import get_connection, init_db, row_to_dict
from app.core.models import (
    Artist,
    ArtistAgency,
    ArtistAgencyCreate,
    ArtistCreate,
    ArtistUpdate,
    ArtistWithSources,
    EventCandidate,
    EventCandidateCreate,
    Source,
    SourceCreate,
    SongLyricsDetail,
    SongLyricsSummary,
    SongCreditsUpdate,
    SpotifyTrackYouTubeLinkCreate,
    WebSongCreate,
    WebSongCreated,
    YouTubePerformanceUpdate,
)
from app.integrations.google_calendar import (
    build_google_auth_url,
    exchange_code_for_tokens,
    google_oauth_configured,
)
from app.lyrics_pipeline.song_service import save_song_from_youtube
from app.lyrics_pipeline.service import LyricsPipelineError
from app.lyrics_pipeline.youtube import extract_youtube_video_id
from app.integrations.youtube_context import fetch_youtube_music_credits
from app.integrations.youtube_live_archive import (
    add_youtube_live_url,
    ensure_youtube_live_korean_labels,
    get_youtube_live_archive,
    list_youtube_performance_filters,
    list_youtube_live_archives,
    search_youtube_song_performances,
    update_youtube_song_performance,
)
from app.integrations.youtube_channel_monitor import backfill_youtube_channel
from app.integrations.spotify import (
    SpotifyAlbumDetail,
    SpotifyAlbumSummary,
    SpotifyApiError,
    SpotifyArtistProfile,
    SpotifyRegisteredArtist,
    SpotifyRelationship,
    get_album_detail,
    get_artist_discography,
    get_spotify_artist,
    search_spotify_artist_candidates,
    spotify_configured,
)
from app.integrations.spotify_youtube import auto_link_spotify_artist_youtube
from app.api.routers.artists import router as artists_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI 시작 시 PostgreSQL 스키마를 준비합니다."""
    if settings.database_url and settings.database_auto_init:
        init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# 새 클라이언트는 /api 경로를 사용합니다. 마이그레이션 중 현재 프론트엔드와
# 기존 링크가 깨지지 않도록 접두사 없는 경로도 한시적으로 유지합니다.
app.include_router(artists_router, prefix="/api")
app.include_router(artists_router)
# 이전 인라인 handler는 소스 수준의 마이그레이션 참고용으로만 보존합니다.
# 실제로 mount하지 않으며, 현재 아티스트 도메인은 router가 담당합니다.
_deprecated_router = APIRouter(include_in_schema=False)
youtube_backfill_tasks: set[asyncio.Task] = set()


class YouTubeLiveCreate(BaseModel):
    youtube_url: HttpUrl
    artist_name: str


class YouTubeChannelBackfillCreate(BaseModel):
    channel_url: HttpUrl
    artist_name: str


@app.get("/health")
def health() -> dict[str, str]:
    """배포된 API 서버가 살아 있는지 확인하는 헬스 체크입니다."""
    return {"status": "ok"}


@_deprecated_router.post("/youtube-lives", status_code=status.HTTP_201_CREATED)
async def create_youtube_live(payload: YouTubeLiveCreate) -> dict:
    try:
        archive_id = await add_youtube_live_url(str(payload.youtube_url), payload.artist_name)
        archive = get_youtube_live_archive(archive_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="YouTube 정보를 가져오지 못했습니다.") from exc
    if archive is None:
        raise HTTPException(status_code=500, detail="저장된 기록을 찾지 못했습니다.")
    return archive


@_deprecated_router.post("/youtube-lives/backfills", status_code=status.HTTP_202_ACCEPTED)
async def create_youtube_live_backfill(payload: YouTubeChannelBackfillCreate) -> dict[str, str]:
    """Start an idempotent historical utawaku collection without blocking the UI."""
    task = asyncio.create_task(
        backfill_youtube_channel(
            channel_url=str(payload.channel_url),
            artist_name=payload.artist_name.strip(),
            concurrency=3,
        )
    )
    youtube_backfill_tasks.add(task)
    task.add_done_callback(youtube_backfill_tasks.discard)
    return {"status": "started", "artist_name": payload.artist_name.strip()}


@_deprecated_router.get("/youtube-lives")
def get_youtube_lives(limit: int = 50, artist_name: str | None = None) -> list[dict]:
    return list_youtube_live_archives(
        limit=max(1, min(limit, 100)), artist_name=artist_name.strip() if artist_name else None
    )


@_deprecated_router.get("/youtube-lives/{archive_id}")
async def get_youtube_live(archive_id: int) -> dict:
    # 오래된 archive에는 한국어 라벨이 없을 수 있으므로 첫 조회 시 채웁니다.
    # 이를 통해 상세 세트리스트가 번역되지 않은 채 남지 않게 합니다.
    await ensure_youtube_live_korean_labels(archive_id)
    archive = get_youtube_live_archive(archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="YouTube 라이브 기록을 찾지 못했습니다.")
    return archive


@_deprecated_router.get("/youtube-performances")
def search_youtube_performances(
    artist_name: list[str] = Query(default=[]),
    song_title: list[str] = Query(default=[]),
    original_artist: list[str] = Query(default=[]),
    limit: int = 200,
) -> list[dict]:
    try:
        return search_youtube_song_performances(
            artist_names=artist_name,
            song_titles=song_title,
            original_artists=original_artist,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@_deprecated_router.get("/youtube-performance-filters")
def get_youtube_performance_filters() -> dict[str, list[str]]:
    return list_youtube_performance_filters()


@_deprecated_router.patch("/youtube-performances/{performance_id}")
def patch_youtube_performance(performance_id: int, payload: YouTubePerformanceUpdate) -> dict:
    try:
        updated = update_youtube_song_performance(
            performance_id, payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="셋리스트 항목을 찾을 수 없습니다.")
    return updated


@_deprecated_router.get("/auth/google/start")
def start_google_auth(discord_user_id: str) -> RedirectResponse:
    """Discord 사용자 ID를 state로 담아 Google OAuth 로그인 화면으로 이동시킵니다."""
    if not google_oauth_configured():
        raise HTTPException(status_code=500, detail="Google OAuth가 설정되어 있지 않습니다.")
    return RedirectResponse(build_google_auth_url(discord_user_id))


@_deprecated_router.get("/auth/google/callback", response_class=HTMLResponse)
async def google_auth_callback(code: str, state: str) -> str:
    """Google OAuth callback에서 인증 code를 토큰으로 바꾸고 연결 완료 HTML을 보여줍니다."""
    await exchange_code_for_tokens(code, state)
    return """
    <html>
      <body>
        <h1>Google Calendar 연결 완료</h1>
        <p>이 페이지를 닫고 Discord로 돌아가도 됩니다.</p>
      </body>
    </html>
    """


@_deprecated_router.get("/artist-agencies", response_model=list[ArtistAgency])
def list_artist_agencies() -> list[dict]:
    """VTuber 소속 필터에 사용할 기업·레이블 목록을 반환합니다."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM artist_agencies ORDER BY name").fetchall()
        return [row_to_dict(row) for row in rows]


@_deprecated_router.post("/artist-agencies", response_model=ArtistAgency, status_code=status.HTTP_201_CREATED)
def create_artist_agency(payload: ArtistAgencyCreate) -> dict:
    """새 VTuber 소속 기업·레이블을 등록합니다."""
    name = payload.name.strip()
    try:
        with get_connection() as conn:
            row = conn.execute(
                "INSERT INTO artist_agencies (name) VALUES (%s) RETURNING *",
                (name,),
            ).fetchone()
            conn.commit()
            return row_to_dict(row)
    except errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="이미 등록된 소속입니다.") from exc


@_deprecated_router.post("/songs/from-youtube", response_model=WebSongCreated, status_code=status.HTTP_201_CREATED)
async def create_song_from_youtube(payload: WebSongCreate) -> dict:
    """등록 아티스트의 YouTube 곡에서 가사·번역·발음을 생성해 저장합니다."""
    with get_connection() as conn:
        artist = conn.execute(
            "SELECT name, display_name FROM artists WHERE id = %s",
            (payload.artist_id,),
        ).fetchone()
    if artist is None:
        raise HTTPException(status_code=404, detail="아티스트를 찾을 수 없습니다.")
    try:
        return await save_song_from_youtube(
            artist=artist["display_name"] or artist["name"],
            title=payload.title.strip(),
            youtube_url=payload.youtube_url.strip(),
            source_mode=payload.source_mode,
            language_code=payload.language_code,
        )
    except (ValueError, LyricsPipelineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@_deprecated_router.get("/songs/lyrics/by-spotify-tracks", response_model=list[SongLyricsSummary])
def list_song_lyrics_by_spotify_tracks(ids: list[str] = Query(default=[])) -> list[SongLyricsSummary]:
    """Return saved lyric records for a set of Spotify track IDs."""
    track_ids = list(dict.fromkeys(track_id for track_id in ids if track_id.strip()))
    if not track_ids:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id AS song_id, s.spotify_track_id, s.youtube_url,
                s.lyricist, s.composer, s.arranger,
                EXISTS (SELECT 1 FROM song_lyrics l WHERE l.song_id = s.id) AS has_lyrics
            FROM songs s
            WHERE s.spotify_track_id = ANY(%s)
            ORDER BY s.updated_at DESC
            """,
            (track_ids,),
        ).fetchall()
    seen: set[str] = set()
    results: list[SongLyricsSummary] = []
    for row in rows:
        track_id = row["spotify_track_id"]
        if track_id in seen:
            continue
        seen.add(track_id)
        results.append(
            SongLyricsSummary(
                song_id=row["song_id"],
                spotify_track_id=track_id,
                youtube_url=row["youtube_url"],
                has_lyrics=row["has_lyrics"],
                lyricist=row["lyricist"],
                composer=row["composer"],
                arranger=row["arranger"],
            )
        )
    return results


@_deprecated_router.post("/songs/spotify-track-youtube", response_model=SongLyricsSummary)
async def link_spotify_track_to_youtube(payload: SpotifyTrackYouTubeLinkCreate) -> SongLyricsSummary:
    """Attach a user-selected YouTube video to a Spotify track without creating lyrics yet."""
    youtube_url = payload.youtube_url.strip()
    try:
        video_id = extract_youtube_video_id(youtube_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="올바른 YouTube 영상 URL을 입력해주세요.") from exc

    try:
        credits = await fetch_youtube_music_credits(video_id)
    except (RuntimeError, httpx.HTTPError):
        credits = None

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT s.id,
                EXISTS (SELECT 1 FROM song_lyrics l WHERE l.song_id = s.id) AS has_lyrics
            FROM songs s
            WHERE s.spotify_track_id = %s
            ORDER BY s.updated_at DESC
            LIMIT 1
            """,
            (payload.spotify_track_id,),
        ).fetchone()
        if existing:
            row = conn.execute(
                """
                UPDATE songs
                SET original_title = %s, artist_name = %s, album_name = %s,
                    youtube_url = %s, youtube_video_id = %s,
                    lyricist = %s, composer = %s, arranger = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, spotify_track_id, youtube_url, lyricist, composer, arranger
                """,
                (payload.title, payload.artist_name, payload.album_name, youtube_url, video_id,
                 credits.lyricist if credits else None, credits.composer if credits else None,
                 credits.arranger if credits else None, existing["id"]),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO songs (
                    discord_user_id, original_title, artist_name, album_name,
                    youtube_url, youtube_video_id, spotify_track_id, lyricist, composer, arranger
                ) VALUES ('web', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, spotify_track_id, youtube_url, lyricist, composer, arranger
                """,
                (payload.title, payload.artist_name, payload.album_name, youtube_url, video_id, payload.spotify_track_id,
                 credits.lyricist if credits else None, credits.composer if credits else None,
                 credits.arranger if credits else None),
            ).fetchone()
        conn.commit()
    has_lyrics = bool(existing["has_lyrics"]) if existing else False
    return SongLyricsSummary(
        song_id=row["id"],
        spotify_track_id=row["spotify_track_id"],
        youtube_url=row["youtube_url"],
        has_lyrics=has_lyrics,
        lyricist=row["lyricist"],
        composer=row["composer"],
        arranger=row["arranger"],
    )


@_deprecated_router.patch("/songs/{song_id}/credits", response_model=SongLyricsSummary)
def update_song_credits(song_id: int, payload: SongCreditsUpdate) -> SongLyricsSummary:
    """Save manually entered song credits when an official description has none."""
    with get_connection() as conn:
        row = conn.execute(
            """
            UPDATE songs
            SET lyricist = %s, composer = %s, arranger = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, spotify_track_id, youtube_url, lyricist, composer, arranger,
                EXISTS (SELECT 1 FROM song_lyrics l WHERE l.song_id = songs.id) AS has_lyrics
            """,
            (payload.lyricist, payload.composer, payload.arranger, song_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Song not found.")
    if not row["spotify_track_id"]:
        raise HTTPException(status_code=409, detail="This song is not linked to a Spotify track.")
    return SongLyricsSummary(
        song_id=row["id"], spotify_track_id=row["spotify_track_id"], youtube_url=row["youtube_url"],
        has_lyrics=row["has_lyrics"], lyricist=row["lyricist"], composer=row["composer"], arranger=row["arranger"],
    )


@_deprecated_router.get("/songs/{song_id}/lyrics", response_model=SongLyricsDetail)
def get_song_lyrics(song_id: int) -> SongLyricsDetail:
    """Return the original lyrics, Korean translation, and pronunciation for one saved song."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                s.id AS song_id, s.original_title, t.title_ko, s.artist_name, s.album_name, s.youtube_url,
                l.original_lyrics, l.translation_ko, l.pronunciation_ko,
                l.lyrics_source_type, l.lyrics_source_url, l.needs_review
            FROM songs s
            JOIN song_lyrics l ON l.song_id = s.id
            LEFT JOIN spotify_track_title_translations t
                ON t.spotify_track_id = s.spotify_track_id
                AND t.original_title = s.original_title
            WHERE s.id = %s
            """,
            (song_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="저장된 가사를 찾을 수 없습니다.")
    return SongLyricsDetail(**row_to_dict(row))


@_deprecated_router.post("/artists", response_model=ArtistWithSources, status_code=status.HTTP_201_CREATED)
def create_artist(payload: ArtistCreate) -> dict:
    """API로 아티스트를 생성하고, X username이 있으면 출처도 함께 저장합니다."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO artists (
                name, display_name, artist_kind, agency, notes,
                show_in_spotify, show_in_lyrics, show_in_youtube_lives
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                payload.name, payload.display_name, payload.artist_kind, payload.agency, payload.notes,
                payload.show_in_spotify, payload.show_in_lyrics, payload.show_in_youtube_lives,
            ),
        )
        artist_id = cursor.fetchone()["id"]

        if payload.x_username:
            conn.execute(
                """
                INSERT INTO artist_sources (artist_id, source_type, label, value)
                VALUES (%s, 'x', 'X account', %s)
                """,
                (artist_id, payload.x_username),
            )

        conn.commit()
        return _get_artist_with_sources(conn, artist_id)


@_deprecated_router.get("/artists", response_model=list[ArtistWithSources])
def list_artists() -> list[dict]:
    """등록된 전체 아티스트와 연결된 출처 목록을 조회합니다."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM artists ORDER BY name").fetchall()
        return [_get_artist_with_sources(conn, row["id"]) for row in rows]


@_deprecated_router.get("/artists/{artist_id}", response_model=ArtistWithSources)
def get_artist(artist_id: int) -> dict:
    """특정 아티스트 한 명과 연결된 출처 목록을 조회합니다."""
    with get_connection() as conn:
        return _get_artist_with_sources(conn, artist_id)


@_deprecated_router.patch("/artists/{artist_id}", response_model=Artist)
def update_artist(artist_id: int, payload: ArtistUpdate) -> dict:
    """아티스트의 이름, 표시 이름, 메모를 부분 수정합니다."""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

    assignments = ", ".join(f"{field} = %s" for field in fields)
    values = list(fields.values())

    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        conn.execute(
            f"""
            UPDATE artists
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            [*values, artist_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM artists WHERE id = %s", (artist_id,)).fetchone()
        return row_to_dict(row)


@_deprecated_router.delete("/artists/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artist(artist_id: int) -> Response:
    """아티스트를 삭제하고 연결된 출처는 DB cascade 설정으로 함께 정리합니다."""
    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        conn.execute("DELETE FROM artists WHERE id = %s", (artist_id,))
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@_deprecated_router.post(
    "/artists/{artist_id}/sources",
    response_model=Source,
    status_code=status.HTTP_201_CREATED,
)
def add_artist_source(artist_id: int, payload: SourceCreate) -> dict:
    """기존 아티스트에 X, 공식 사이트, 예매 사이트 같은 출처를 추가합니다."""
    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        try:
            cursor = conn.execute(
                """
                INSERT INTO artist_sources (artist_id, source_type, label, value, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    artist_id,
                    payload.source_type,
                    payload.label,
                    payload.value,
                    payload.is_active,
                ),
            )
            source_id = cursor.fetchone()["id"]
            conn.commit()
        except errors.UniqueViolation as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail="이미 등록된 출처입니다.") from exc

        row = conn.execute(
            "SELECT * FROM artist_sources WHERE id = %s",
            (source_id,),
        ).fetchone()
        return _source_row_to_dict(row)


@_deprecated_router.get("/artists/{artist_id}/sources", response_model=list[Source])
def list_artist_sources(artist_id: int) -> list[dict]:
    """특정 아티스트에 등록된 출처 목록을 조회합니다."""
    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        rows = conn.execute(
            """
            SELECT * FROM artist_sources
            WHERE artist_id = %s
            ORDER BY source_type, value
            """,
            (artist_id,),
        ).fetchall()
        return [_source_row_to_dict(row) for row in rows]


@_deprecated_router.delete("/artists/{artist_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artist_source(artist_id: int, source_id: int) -> Response:
    """특정 아티스트에 연결된 출처 하나를 삭제합니다."""
    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        cursor = conn.execute(
            "DELETE FROM artist_sources WHERE id = %s AND artist_id = %s",
            (source_id, artist_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="출처를 찾을 수 없습니다.")
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@_deprecated_router.post("/event-candidates", response_model=EventCandidate, status_code=status.HTTP_201_CREATED)
def create_event_candidate(payload: EventCandidateCreate) -> dict:
    """수동 또는 agent가 만든 공연/예매 일정 후보를 저장합니다."""
    data = payload.model_dump()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO event_candidates (
                artist_id, source_id, event_type, event_format, title, starts_at, venue, ticket_opens_at,
                ticket_closes_at, ticket_url, price_text, source_url, raw_text, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["artist_id"],
                data["source_id"],
                data["event_type"],
                data["event_format"],
                data["title"],
                data["starts_at"],
                data["venue"],
                data["ticket_opens_at"],
                data["ticket_closes_at"],
                data["ticket_url"],
                data["price_text"],
                data["source_url"],
                data["raw_text"],
                data["status"],
            ),
        )
        event_candidate_id = cursor.fetchone()["id"]
        conn.commit()
        row = conn.execute(
            "SELECT * FROM event_candidates WHERE id = %s",
            (event_candidate_id,),
        ).fetchone()
        return row_to_dict(row)


@_deprecated_router.get("/event-candidates", response_model=list[EventCandidate])
def list_event_candidates(
    status_filter: str | None = None,
    artist_id: int | None = None,
    event_type: str | None = None,
    event_format: str | None = None,
) -> list[dict]:
    """저장된 일정 후보를 조회하고, status_filter가 있으면 해당 상태만 반환합니다."""
    with get_connection() as conn:
        clauses: list[str] = []
        params: list[object] = []
        if status_filter:
            clauses.append("status = %s")
            params.append(status_filter)
        if artist_id is not None:
            clauses.append("artist_id = %s")
            params.append(artist_id)
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        if event_format:
            clauses.append("event_format = %s")
            params.append(event_format)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM event_candidates{where} ORDER BY created_at DESC",
            tuple(params),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@_deprecated_router.get("/spotify/artists", response_model=list[SpotifyRegisteredArtist])
def list_spotify_artists() -> list[SpotifyRegisteredArtist]:
    """등록 아티스트와 현재 Spotify 매칭 상태를 반환합니다."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id, name, display_name, artist_kind, agency, spotify_artist_id, spotify_name,
                spotify_image_url, spotify_url
            FROM artists
            WHERE spotify_sync_enabled = TRUE AND show_in_spotify = TRUE
            ORDER BY COALESCE(display_name, name)
            """
        ).fetchall()
    return [
        SpotifyRegisteredArtist(
            local_artist_id=row["id"],
            related_artist_ids=row["related_artist_ids"],
            local_name=row["display_name"] or row["name"],
            artist_kind=row["artist_kind"],
            agency=row["agency"],
            spotify_artist_id=row["spotify_artist_id"],
            spotify_name=row["spotify_name"],
            image_url=row["spotify_image_url"],
            spotify_url=row["spotify_url"],
            matched=bool(row["spotify_artist_id"]),
        )
        for row in group_artists(rows)
    ]


@_deprecated_router.get(
    "/spotify/artists/{artist_id}/candidates",
    response_model=list[SpotifyArtistProfile],
)
async def get_spotify_artist_candidates(artist_id: int) -> list[SpotifyArtistProfile]:
    """로컬 아티스트 이름에 대한 Spotify 매칭 후보를 반환합니다."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, display_name FROM artists WHERE id = %s AND spotify_sync_enabled = TRUE",
            (artist_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Spotify 동기화 대상 아티스트를 찾을 수 없습니다.")
    try:
        candidates = await search_spotify_artist_candidates(
            row["id"], row["display_name"] or row["name"]
        )
        if not candidates and row["display_name"]:
            candidates = await search_spotify_artist_candidates(row["id"], row["name"])
        return candidates
    except SpotifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@_deprecated_router.get("/spotify/artists/{artist_id}/profile", response_model=SpotifyArtistProfile)
async def get_spotify_artist_profile(artist_id: int) -> SpotifyArtistProfile:
    """Fetch the latest Spotify profile metadata for one matched artist."""
    if not spotify_configured():
        raise HTTPException(status_code=503, detail="Spotify API가 설정되어 있지 않습니다.")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT spotify_artist_id FROM artists WHERE id = %s",
            (artist_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="아티스트를 찾을 수 없습니다.")
    if not row["spotify_artist_id"]:
        raise HTTPException(status_code=409, detail="Spotify 아티스트 매칭이 필요합니다.")

    try:
        return await get_spotify_artist(artist_id, row["spotify_artist_id"])
    except SpotifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@_deprecated_router.post("/spotify/artists/{artist_id}/sync", response_model=SpotifyRegisteredArtist)
async def sync_spotify_artist(
    artist_id: int,
    spotify_artist_id: str,
) -> SpotifyRegisteredArtist:
    """사용자가 선택한 Spotify 아티스트를 로컬 아티스트에 매칭합니다."""
    if not spotify_configured():
        raise HTTPException(status_code=503, detail="Spotify API가 설정되어 있지 않습니다.")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, display_name FROM artists WHERE id = %s AND spotify_sync_enabled = TRUE",
            (artist_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Spotify 동기화 대상 아티스트를 찾을 수 없습니다.")

    try:
        profile = await get_spotify_artist(row["id"], spotify_artist_id)
    except SpotifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    with get_connection() as conn:
        conn.execute(
                """
                UPDATE artists
                SET spotify_artist_id = %s,
                    spotify_name = %s,
                    spotify_image_url = %s,
                    spotify_url = %s,
                    spotify_match_updated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
            (
                profile.spotify_artist_id,
                profile.name,
                profile.image_url,
                profile.spotify_url,
                row["id"],
            ),
        )
        conn.commit()
    # Spotify 연결을 확정할 때만 자동 검색한다. 신뢰도 기준을 통과하지
    # 못한 트랙은 저장하지 않아, 화면의 수동 YouTube 연결 버튼으로 남는다.
    try:
        auto_links = await auto_link_spotify_artist_youtube(profile.spotify_artist_id)
    except (SpotifyApiError, RuntimeError, httpx.HTTPError):
        # 영상 검색 실패가 Spotify 연결 자체를 실패시키면 안 된다.
        auto_links = None

    artist = next(artist for artist in list_spotify_artists() if artist.local_artist_id == artist_id)
    if auto_links is None:
        return artist
    return artist.model_copy(
        update={
            "youtube_auto_linked": auto_links.linked,
            "youtube_auto_unmatched": auto_links.unmatched,
            "youtube_auto_link_enabled": auto_links.enabled,
        }
    )


@_deprecated_router.post("/spotify/artists/{artist_id}/youtube-auto-link", response_model=SpotifyRegisteredArtist)
async def auto_link_existing_spotify_artist_youtube(artist_id: int) -> SpotifyRegisteredArtist:
    """Run the automatic YouTube matcher again for an already linked artist."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT spotify_artist_id FROM artists WHERE id = %s",
            (artist_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Artist not found.")
    if not row["spotify_artist_id"]:
        raise HTTPException(status_code=409, detail="Connect a Spotify artist first.")

    try:
        auto_links = await auto_link_spotify_artist_youtube(row["spotify_artist_id"])
    except SpotifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    artist = next(item for item in list_spotify_artists() if item.local_artist_id == artist_id)
    return artist.model_copy(
        update={
            "youtube_auto_linked": auto_links.linked,
            "youtube_auto_unmatched": auto_links.unmatched,
            "youtube_auto_link_enabled": auto_links.enabled,
        }
    )


@_deprecated_router.delete("/spotify/artists/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def exclude_spotify_artist(artist_id: int) -> Response:
    """Spotify 매칭을 지우고 이후 전체 동기화 대상에서도 제외합니다."""
    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        conn.execute(
            """
            UPDATE artists
            SET spotify_sync_enabled = FALSE,
                spotify_artist_id = NULL,
                spotify_name = NULL,
                spotify_image_url = NULL,
                spotify_url = NULL,
                spotify_match_updated_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (artist_id,),
        )
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@_deprecated_router.post("/spotify/artists/{artist_id}/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_spotify_artist(artist_id: int) -> Response:
    """제외한 아티스트를 Spotify 전체 동기화 대상에 다시 포함합니다."""
    with get_connection() as conn:
        _ensure_artist_exists(conn, artist_id)
        conn.execute(
            """
            UPDATE artists
            SET spotify_sync_enabled = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (artist_id,),
        )
        conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@_deprecated_router.get(
    "/spotify/artists/{artist_id}/discography",
    response_model=list[SpotifyAlbumSummary],
)
async def get_spotify_discography(artist_id: int) -> list[SpotifyAlbumSummary]:
    """등록 아티스트의 앨범, 싱글, 참여작 전체를 Spotify에서 조회합니다."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT spotify_artist_id FROM artists WHERE id = %s",
            (artist_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="아티스트를 찾을 수 없습니다.")
    if not row["spotify_artist_id"]:
        raise HTTPException(status_code=409, detail="Spotify 아티스트 매칭이 필요합니다.")
    return await get_artist_discography(row["spotify_artist_id"])


@_deprecated_router.get("/spotify/albums/{album_id}", response_model=SpotifyAlbumDetail)
async def get_spotify_album(album_id: str) -> SpotifyAlbumDetail:
    """한 앨범 또는 싱글의 전체 수록곡을 반환합니다."""
    if not spotify_configured():
        raise HTTPException(status_code=503, detail="Spotify API가 설정되어 있지 않습니다.")
    try:
        return await get_album_detail(album_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Spotify 앨범 조회에 실패했습니다.") from exc


@_deprecated_router.get("/spotify/relationships", response_model=list[SpotifyRelationship])
async def get_spotify_relationships() -> list[SpotifyRelationship]:
    """공동 앨범·싱글 크레딧을 이용해 등록 아티스트 사이의 연결을 계산합니다."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, spotify_artist_id
            FROM artists
            WHERE spotify_artist_id IS NOT NULL
            ORDER BY id
            """
        ).fetchall()
    spotify_to_local = {row["spotify_artist_id"]: row["id"] for row in rows}
    relationships: dict[tuple[int, int], SpotifyRelationship] = {}
    for row in rows:
        albums = await get_artist_discography(row["spotify_artist_id"])
        for album in albums:
            for collaborator_id in album.artist_ids:
                target_id = spotify_to_local.get(collaborator_id)
                if target_id is None or target_id == row["id"]:
                    continue
                source_id, related_id = sorted((row["id"], target_id))
                key = (source_id, related_id)
                relation = relationships.setdefault(
                    key,
                    SpotifyRelationship(
                        source_artist_id=source_id,
                        target_artist_id=related_id,
                        strength=0,
                    ),
                )
                if album.name not in relation.shared_releases:
                    relation.shared_releases.append(album.name)
                    relation.strength += 1
    return sorted(
        relationships.values(),
        key=lambda relation: (-relation.strength, relation.source_artist_id),
    )


def _ensure_artist_exists(conn: Connection, artist_id: int) -> None:
    """아티스트가 실제로 존재하는지 확인하고 없으면 404 에러를 발생시킵니다."""
    row = conn.execute("SELECT id FROM artists WHERE id = %s", (artist_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="아티스트를 찾을 수 없습니다.")


def _get_artist_with_sources(conn: Connection, artist_id: int) -> dict:
    """아티스트 기본 정보에 출처 목록을 붙여 API 응답 형태로 만듭니다."""
    artist = row_to_dict(
        conn.execute("SELECT * FROM artists WHERE id = %s", (artist_id,)).fetchone()
    )
    if artist is None:
        raise HTTPException(status_code=404, detail="아티스트를 찾을 수 없습니다.")

    sources = conn.execute(
        """
        SELECT * FROM artist_sources
        WHERE artist_id = %s
        ORDER BY source_type, value
        """,
        (artist_id,),
    ).fetchall()
    artist["sources"] = [_source_row_to_dict(row) for row in sources]
    representative = conn.execute(
        """
        SELECT y.youtube_url
        FROM youtube_live_archives y
        LEFT JOIN artist_sources s ON s.id = y.source_id
        WHERE s.artist_id = %s
           OR (s.id IS NULL AND LOWER(COALESCE(y.performer_name, '')) = LOWER(%s))
        ORDER BY COALESCE(y.broadcast_at, y.published_at) DESC NULLS LAST, y.id DESC
        LIMIT 1
        """,
        (artist_id, artist["name"]),
    ).fetchone()
    artist["representative_youtube_url"] = representative["youtube_url"] if representative else None
    return artist


def _source_row_to_dict(row: dict | None) -> dict:
    """DB에서 읽은 출처 row를 API 응답용 dict로 변환합니다."""
    source = row_to_dict(row)
    if source is None:
        raise HTTPException(status_code=404, detail="출처를 찾을 수 없습니다.")
    return source


# 호환성 모듈에서 endpoint 함수를 단계적으로 추출할 때 순환 import를 피하려고
# handler 정의 뒤에 router를 import합니다.
from app.api.routers.auth import router as auth_router
from app.api.routers.songs import router as songs_router
from app.api.routers.spotify import router as spotify_router
from app.api.routers.youtube import router as youtube_router

for _router in (auth_router, songs_router, spotify_router, youtube_router):
    app.include_router(_router, prefix="/api")
    app.include_router(_router)
