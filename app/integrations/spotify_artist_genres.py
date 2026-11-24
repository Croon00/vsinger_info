"""Artist-level genres as Spotify publishes them; never applied to individual songs."""
import asyncio
from datetime import datetime

from pydantic import BaseModel, Field

from app.integrations.spotify_catalog import SPOTIFY_ID, SpotifyFailure

MAX_GENRES = 20


class SpotifyArtistGenres(BaseModel):
    spotify_artist_id: str = Field(pattern=SPOTIFY_ID)
    genres: list[str] = Field(default_factory=list, max_length=MAX_GENRES)
    captured_at: datetime


def normalize_genres(value) -> list[str] | None:
    """Lower-case, trimmed, de-duplicated names; None when the field is absent or malformed."""
    if not isinstance(value, list):
        return None
    genres = [item.strip().casefold() for item in value if isinstance(item, str) and item.strip()]
    return list(dict.fromkeys(genres))[:MAX_GENRES]


async def _artist(client, spotify_id, retries, sleep):
    for attempt in range(retries + 1):
        try:
            return await client.get(f'/artists/{spotify_id}')
        except SpotifyFailure as exc:
            if not exc.retry:
                return None  # Removed or unavailable artist: skip it, keep the stored value.
            if attempt == retries:
                raise
            await sleep(min(60.0, max(exc.retry_after, 2.0 ** (attempt + 1))))


async def fetch_genres(client, ids, captured_at, *, retries=3, sleep=asyncio.sleep) -> list[SpotifyArtistGenres]:
    """One ``/artists/{id}`` read per account. An artist whose response has no ``genres``
    field, or that Spotify no longer serves, is left out so a stored value is never
    replaced by a guessed empty list. Transient failures are retried, then stop the run."""
    rows = []
    for spotify_id in dict.fromkeys(ids):
        data = await _artist(client, spotify_id, retries, sleep)
        if data is None:
            continue
        if data.get('id') != spotify_id:
            raise ValueError('Unrequested Spotify artist')
        genres = normalize_genres(data.get('genres'))
        if genres is not None:
            rows.append(SpotifyArtistGenres(spotify_artist_id=spotify_id, genres=genres, captured_at=captured_at))
    return rows
