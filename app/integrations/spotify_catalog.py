"""Bounded, ID-only Spotify catalog reads. No artist search or translation."""
from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field


SPOTIFY_ID = r'^[A-Za-z0-9]{22}$'


class SpotifyFailure(Exception):
    def __init__(self, code: str, *, retry: bool = False, retry_after: float = 0):
        super().__init__(code)
        self.retry, self.retry_after = retry, retry_after


class SpotifyTrack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=SPOTIFY_ID)
    title: str = Field(min_length=1)
    artist_ids: list[str]
    disc_number: int = Field(ge=1)
    track_number: int = Field(ge=1)
    duration_ms: int | None = Field(default=None, ge=0)
    raw: dict


class SpotifyAlbum(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=SPOTIFY_ID)
    title: str = Field(min_length=1)
    album_type: str
    release_year: int | None = None
    release_month: int | None = None
    release_day: int | None = None
    cover_image_url: str | None = None
    artist_ids: list[str]
    tracks: list[SpotifyTrack]
    raw: dict


def _ids(artists) -> list[str]:
    if not isinstance(artists, list):
        raise ValueError('artists is not a list')
    result = [artist['id'] for artist in artists]
    if any(not isinstance(value, str) or len(value) != 22 or not value.isalnum() for value in result):
        raise ValueError('invalid artist id')
    return result


def album_from_api(raw: dict, track_items: list[dict]) -> SpotifyAlbum:
    """Reject incomplete batches rather than silently persist a partial album."""
    if not isinstance(raw, dict) or not isinstance(track_items, list):
        raise ValueError('invalid album')
    release = raw.get('release_date') or ''
    precision = raw.get('release_date_precision')
    if precision not in ('year', 'month', 'day') or not isinstance(release, str):
        raise ValueError('invalid release precision')
    parts = release.split('-')
    expected = {'year': 1, 'month': 2, 'day': 3}[precision]
    if len(parts) != expected or any(not part.isdigit() for part in parts):
        raise ValueError('invalid release date')
    year, month, day = (int(parts[0]), int(parts[1]) if expected > 1 else None,
                        int(parts[2]) if expected > 2 else None)
    if not 1 <= year <= 9999 or (month and not 1 <= month <= 12):
        raise ValueError('invalid release date')
    if day:
        from datetime import date
        date(year, month, day)
    images = raw.get('images') or []
    cover = images[0].get('url') if images else None
    if cover is not None and (not isinstance(cover, str) or not cover.startswith('https://')):
        cover = None
    tracks = [SpotifyTrack(id=item['id'], title=item['name'], artist_ids=_ids(item['artists']),
                           disc_number=item['disc_number'], track_number=item['track_number'],
                           duration_ms=item.get('duration_ms'), raw=item) for item in track_items]
    if not isinstance(raw.get('name'), str) or not raw['name'].strip() or any(not track.title.strip() for track in tracks):
        raise ValueError('empty album or track title')
    if len({(track.disc_number, track.track_number) for track in tracks}) != len(tracks):
        raise ValueError('duplicate track position')
    if len({track.id for track in tracks}) != len(tracks):
        raise ValueError('duplicate Spotify track ID')
    return SpotifyAlbum(id=raw['id'], title=raw['name'], album_type=raw['album_type'],
                        release_year=year, release_month=month, release_day=day,
                        cover_image_url=cover, artist_ids=_ids(raw['artists']), tracks=tracks, raw=raw)


class SpotifyCatalogClient:
    def __init__(self, client_id: str, client_secret: str, *, transport=None, interval_seconds: float = 1):
        self.client_id, self.client_secret = client_id, client_secret
        self.transport, self.interval_seconds = transport, interval_seconds
        self.last_request = 0.0
        self.token = None

    async def _request(self, method: str, url: str, *, headers=None, params=None, data=None):
        loop = asyncio.get_running_loop()
        await asyncio.sleep(max(0, self.interval_seconds - (loop.time() - self.last_request)))
        self.last_request = loop.time()
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                response = await client.request(method, url, headers=headers, params=params, data=data)
        except httpx.TransportError:
            raise SpotifyFailure('transport', retry=True) from None
        if response.is_error:
            retry = response.status_code == 429 or response.status_code >= 500
            delay = 0.0
            header = response.headers.get('Retry-After', '')
            try:
                delay = max(0, float(header))
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
                except (ValueError, TypeError):
                    pass
            raise SpotifyFailure('rate_limited' if response.status_code == 429 else
                                 'provider_error', retry=retry, retry_after=delay)
        try:
            value = response.json()
        except ValueError:
            raise SpotifyFailure('malformed_response') from None
        if not isinstance(value, dict):
            raise SpotifyFailure('malformed_response')
        return value

    async def _token(self):
        if self.token:
            return self.token
        if not self.client_id or not self.client_secret:
            raise SpotifyFailure('missing_credentials')
        basic = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode()
        data = await self._request('POST', 'https://accounts.spotify.com/api/token',
                                   headers={'Authorization': 'Basic ' + basic},
                                   data={'grant_type': 'client_credentials'})
        token = data.get('access_token')
        if not isinstance(token, str) or not token:
            raise SpotifyFailure('malformed_token')
        self.token = token
        return token

    async def get(self, path: str, *, params=None):
        token = await self._token()
        return await self._request('GET', 'https://api.spotify.com/v1' + path,
                                   headers={'Authorization': 'Bearer ' + token}, params=params)

    async def albums_page(self, artist_id: str, *, offset: int) -> tuple[list[dict], bool]:
        data = await self.get(f'/artists/{artist_id}/albums', params={'include_groups': 'album,single,appears_on,compilation',
                          'market': 'KR', 'limit': 10, 'offset': offset})
        items = data.get('items')
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise SpotifyFailure('malformed_albums')
        if data.get('next') and not items:
            raise SpotifyFailure('incomplete_album_page')
        return items, bool(data.get('next'))

    async def album(self, album_id: str) -> SpotifyAlbum:
        raw = await self.get(f'/albums/{album_id}', params={'market': 'KR'})
        tracks, offset = [], 0
        for _ in range(4):
            page = await self.get(f'/albums/{album_id}/tracks', params={'market': 'KR', 'limit': 50, 'offset': offset})
            items = page.get('items')
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise SpotifyFailure('malformed_tracks')
            tracks.extend(items)
            if not page.get('next'):
                break
            offset += 50
        else:
            raise SpotifyFailure('track_page_limit')
        if len(tracks) != raw.get('total_tracks'):
            raise SpotifyFailure('incomplete_album')
        try:
            return album_from_api(raw, tracks)
        except (KeyError, TypeError, ValueError) as exc:
            raise SpotifyFailure('malformed_album') from None
