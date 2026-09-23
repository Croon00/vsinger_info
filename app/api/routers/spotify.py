"""Spotify HTTP endpoints, independent of application startup."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from psycopg import Connection

from app.core.artist_identity import group_artists
from app.core.db import get_connection
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

router = APIRouter(tags=["spotify"])


@router.get("/spotify/artists", response_model=list[SpotifyRegisteredArtist])
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


@router.get(
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


@router.get("/spotify/artists/{artist_id}/profile", response_model=SpotifyArtistProfile)
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


@router.post("/spotify/artists/{artist_id}/sync", response_model=SpotifyRegisteredArtist)
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


@router.post("/spotify/artists/{artist_id}/youtube-auto-link", response_model=SpotifyRegisteredArtist)
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


@router.delete("/spotify/artists/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post("/spotify/artists/{artist_id}/enable", status_code=status.HTTP_204_NO_CONTENT)
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


@router.get(
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


@router.get("/spotify/albums/{album_id}", response_model=SpotifyAlbumDetail)
async def get_spotify_album(album_id: str) -> SpotifyAlbumDetail:
    """한 앨범 또는 싱글의 전체 수록곡을 반환합니다."""
    if not spotify_configured():
        raise HTTPException(status_code=503, detail="Spotify API가 설정되어 있지 않습니다.")
    try:
        return await get_album_detail(album_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Spotify 앨범 조회에 실패했습니다.") from exc


@router.get("/spotify/relationships", response_model=list[SpotifyRelationship])
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
