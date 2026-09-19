from __future__ import annotations

import base64
import asyncio
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_API_URL = "https://api.spotify.com/v1"


class SpotifyApiError(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class SpotifyTrackInfo(BaseModel):
    """Spotify 검색 결과에서 곡 저장에 필요한 핵심 메타데이터입니다."""

    model_config = ConfigDict(frozen=True)

    track_id: str = Field(min_length=1)
    name: str
    artists: list[str]
    artist_ids: list[str]
    album_id: str | None = None
    album_name: str | None = None
    release_date: str | None = None
    duration_ms: int | None = None
    spotify_url: str | None = None
    cover_image_url: str | None = None
    raw: dict[str, Any]


class SpotifyArtistProfile(BaseModel):
    local_artist_id: int
    spotify_artist_id: str
    name: str
    image_url: str | None = None
    spotify_url: str | None = None
    genres: list[str] = Field(default_factory=list)


class SpotifyAlbumSummary(BaseModel):
    id: str
    name: str
    album_type: str
    release_date: str | None = None
    release_date_precision: str | None = None
    total_tracks: int = 0
    image_url: str | None = None
    spotify_url: str | None = None
    artists: list[str] = Field(default_factory=list)
    artist_ids: list[str] = Field(default_factory=list)


class SpotifyTrackSummary(BaseModel):
    id: str
    name: str
    name_ko: str | None = None
    track_number: int
    disc_number: int
    duration_ms: int | None = None
    explicit: bool = False
    spotify_url: str | None = None
    artists: list[str] = Field(default_factory=list)
    artist_ids: list[str] = Field(default_factory=list)


class SpotifyAlbumDetail(SpotifyAlbumSummary):
    tracks: list[SpotifyTrackSummary] = Field(default_factory=list)


class SpotifyDiscographyTrack(SpotifyTrackSummary):
    """A Spotify track with the release name needed for YouTube matching."""

    album_name: str


class SpotifyRelationship(BaseModel):
    source_artist_id: int
    target_artist_id: int
    strength: int
    shared_releases: list[str] = Field(default_factory=list)


class SpotifyRegisteredArtist(BaseModel):
    local_artist_id: int
    related_artist_ids: list[int] = Field(default_factory=list)
    local_name: str
    artist_kind: str
    agency: str | None = None
    spotify_artist_id: str | None = None
    spotify_name: str | None = None
    image_url: str | None = None
    spotify_url: str | None = None
    matched: bool = False
    youtube_auto_linked: int = 0
    youtube_auto_unmatched: int = 0
    youtube_auto_link_enabled: bool = True


def spotify_configured() -> bool:
    return bool(settings.spotify_client_id and settings.spotify_client_secret)


async def _get_spotify_access_token() -> str:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise RuntimeError("Spotify API credentials are not configured.")

    credentials = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            headers={"Authorization": f"Basic {encoded}"},
            data={"grant_type": "client_credentials"},
        )
        response.raise_for_status()
        data = response.json()
    return str(data["access_token"])


async def search_spotify_track(artist: str, title: str) -> SpotifyTrackInfo | None:
    """아티스트명과 곡 제목으로 Spotify track을 검색해 첫 번째 후보를 반환합니다."""
    if not spotify_configured():
        return None

    token = await _get_spotify_access_token()
    query = f'track:"{title}" artist:"{artist}"'
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            SPOTIFY_SEARCH_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "track", "limit": 1},
        )
        response.raise_for_status()
        data = response.json()

    items = ((data.get("tracks") or {}).get("items") or [])
    if not items:
        return None
    return spotify_track_from_api_item(items[0])


async def search_spotify_artist(local_artist_id: int, name: str) -> SpotifyArtistProfile | None:
    """Resolve one local artist to the closest Spotify artist search result."""
    token = await _get_spotify_access_token()
    data = await _spotify_get(
        "/search",
        token,
        params={"q": f'artist:"{name}"', "type": "artist", "limit": 5},
    )
    items = ((data.get("artists") or {}).get("items") or [])
    if not items:
        return None

    normalized = _normalize_name(name)
    best = min(
        items,
        key=lambda item: (
            0 if _normalize_name(str(item.get("name") or "")) == normalized else 1,
            len(str(item.get("name") or "")),
        ),
    )
    return spotify_artist_from_api_item(local_artist_id, best)


async def search_spotify_artist_candidates(
    local_artist_id: int,
    name: str,
    *,
    limit: int = 5,
) -> list[SpotifyArtistProfile]:
    """사용자가 직접 고를 수 있도록 Spotify 아티스트 검색 후보를 반환합니다."""
    token = await _get_spotify_access_token()
    data = await _spotify_get(
        "/search",
        token,
        params={"q": f'artist:"{name}"', "type": "artist", "limit": limit},
    )
    items = ((data.get("artists") or {}).get("items") or [])
    return [spotify_artist_from_api_item(local_artist_id, item) for item in items]


async def get_spotify_artist(
    local_artist_id: int,
    spotify_artist_id: str,
) -> SpotifyArtistProfile:
    token = await _get_spotify_access_token()
    item = await _spotify_get(f"/artists/{spotify_artist_id}", token)
    return spotify_artist_from_api_item(local_artist_id, item)


async def get_artist_discography(
    spotify_artist_id: str,
    *,
    include_groups: str = "album,single,appears_on,compilation",
) -> list[SpotifyAlbumSummary]:
    """Fetch every album page for one Spotify artist and remove market duplicates."""
    token = await _get_spotify_access_token()
    items = await _spotify_get_all_pages(
        f"/artists/{spotify_artist_id}/albums",
        token,
        params={"include_groups": include_groups, "market": "KR", "limit": 10},
    )
    unique: dict[str, SpotifyAlbumSummary] = {}
    for item in items:
        album = spotify_album_from_api_item(item)
        existing = unique.get(album.id)
        if existing is None or (album.release_date or "") > (existing.release_date or ""):
            unique[album.id] = album
    return sorted(
        unique.values(),
        key=lambda album: (album.release_date or "", album.name),
        reverse=True,
    )


async def get_album_detail(album_id: str) -> SpotifyAlbumDetail:
    token = await _get_spotify_access_token()
    album, track_items = await asyncio.gather(
        _spotify_get(f"/albums/{album_id}", token, params={"market": "KR"}),
        _spotify_get_all_pages(
            f"/albums/{album_id}/tracks",
            token,
            params={"market": "KR", "limit": 50},
        ),
    )
    summary = spotify_album_from_api_item(album)
    tracks = [spotify_track_summary_from_api_item(item) for item in track_items]
    from app.integrations.spotify_title_translation import resolve_korean_track_titles

    try:
        translations = await resolve_korean_track_titles([(track.id, track.name) for track in tracks])
    except Exception:
        # 제목 번역 실패가 Spotify 앨범 조회 자체를 막으면 안 됩니다.
        # 번역하지 못한 이름은 원문 그대로 표시합니다.
        translations = {}
    tracks = [track.model_copy(update={"name_ko": translations.get(track.id)}) for track in tracks]
    return SpotifyAlbumDetail(**summary.model_dump(), tracks=tracks)


async def get_artist_discography_tracks(
    spotify_artist_id: str,
    *,
    include_groups: str = "album,single",
) -> list[SpotifyDiscographyTrack]:
    """Fetch an artist's own release tracks with one Spotify access token.

    This is deliberately separate from the UI album-detail fetch: automatic
    YouTube matching needs a one-off complete track list when an artist is
    connected.
    """
    token = await _get_spotify_access_token()
    album_items = await _spotify_get_all_pages(
        f"/artists/{spotify_artist_id}/albums",
        token,
        params={"include_groups": include_groups, "market": "KR", "limit": 50},
    )
    albums: dict[str, SpotifyAlbumSummary] = {}
    for item in album_items:
        album = spotify_album_from_api_item(item)
        albums.setdefault(album.id, album)

    semaphore = asyncio.Semaphore(8)

    async def fetch_tracks(album: SpotifyAlbumSummary) -> list[SpotifyDiscographyTrack]:
        async with semaphore:
            items = await _spotify_get_all_pages(
                f"/albums/{album.id}/tracks",
                token,
                params={"market": "KR", "limit": 50},
            )
        return [
            SpotifyDiscographyTrack(
                **spotify_track_summary_from_api_item(item).model_dump(),
                album_name=album.name,
            )
            for item in items
        ]

    track_groups = await asyncio.gather(*(fetch_tracks(album) for album in albums.values()))
    unique: dict[str, SpotifyDiscographyTrack] = {}
    for tracks in track_groups:
        for track in tracks:
            unique.setdefault(track.id, track)
    return list(unique.values())


async def _spotify_get(
    path: str,
    token: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{SPOTIFY_API_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        if response.is_error:
            detail = response.text.strip() or f"Spotify API error ({response.status_code})"
            raise SpotifyApiError(detail, response.status_code)
        return response.json()


async def _spotify_get_all_pages(
    path: str,
    token: str,
    *,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    offset = 0
    limit = int(params.get("limit", 10))
    while True:
        data = await _spotify_get(path, token, params={**params, "offset": offset})
        items = list(data.get("items") or [])
        results.extend(items)
        if not data.get("next") or not items:
            return results
        offset += limit


def spotify_artist_from_api_item(
    local_artist_id: int,
    item: dict[str, Any],
) -> SpotifyArtistProfile:
    images = item.get("images") or []
    return SpotifyArtistProfile(
        local_artist_id=local_artist_id,
        spotify_artist_id=str(item["id"]),
        name=str(item.get("name") or ""),
        image_url=(images[0] or {}).get("url") if images else None,
        spotify_url=(item.get("external_urls") or {}).get("spotify"),
        genres=[str(genre) for genre in item.get("genres") or []],
    )


def spotify_album_from_api_item(item: dict[str, Any]) -> SpotifyAlbumSummary:
    images = item.get("images") or []
    artists = item.get("artists") or []
    return SpotifyAlbumSummary(
        id=str(item["id"]),
        name=str(item.get("name") or ""),
        album_type=str(item.get("album_type") or "album"),
        release_date=item.get("release_date"),
        release_date_precision=item.get("release_date_precision"),
        total_tracks=int(item.get("total_tracks") or 0),
        image_url=(images[0] or {}).get("url") if images else None,
        spotify_url=(item.get("external_urls") or {}).get("spotify"),
        artists=[str(artist.get("name") or "") for artist in artists if artist.get("name")],
        artist_ids=[str(artist.get("id") or "") for artist in artists if artist.get("id")],
    )


def spotify_track_summary_from_api_item(item: dict[str, Any]) -> SpotifyTrackSummary:
    artists = item.get("artists") or []
    return SpotifyTrackSummary(
        id=str(item["id"]),
        name=str(item.get("name") or ""),
        track_number=int(item.get("track_number") or 0),
        disc_number=int(item.get("disc_number") or 1),
        duration_ms=item.get("duration_ms"),
        explicit=bool(item.get("explicit")),
        spotify_url=(item.get("external_urls") or {}).get("spotify"),
        artists=[str(artist.get("name") or "") for artist in artists if artist.get("name")],
        artist_ids=[str(artist.get("id") or "") for artist in artists if artist.get("id")],
    )


def _normalize_name(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def spotify_track_from_api_item(item: dict[str, Any]) -> SpotifyTrackInfo:
    album = item.get("album") or {}
    artists = item.get("artists") or []
    images = album.get("images") or []
    external_urls = item.get("external_urls") or {}

    return SpotifyTrackInfo(
        track_id=str(item["id"]),
        name=str(item.get("name") or ""),
        artists=[str(artist.get("name") or "") for artist in artists if artist.get("name")],
        artist_ids=[str(artist.get("id") or "") for artist in artists if artist.get("id")],
        album_id=album.get("id"),
        album_name=album.get("name"),
        release_date=album.get("release_date"),
        duration_ms=item.get("duration_ms"),
        spotify_url=external_urls.get("spotify"),
        cover_image_url=(images[0] or {}).get("url") if images else None,
        raw=item,
    )
