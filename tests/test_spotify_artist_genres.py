import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.integrations.spotify_artist_genres import fetch_genres, normalize_genres
from app.integrations.spotify_catalog import SpotifyFailure
from app.schemas.read_models import ArtistRead

A, B, C = 'a' * 22, 'b' * 22, 'c' * 22


def test_genres_are_normalized_and_missing_field_is_not_an_empty_list():
    captured = datetime.now(UTC)
    client = AsyncMock()
    client.get.side_effect = [
        {'id': A, 'genres': [' J-Pop ', 'anime', 'j-pop', '', 3]},
        {'id': B, 'genres': []},
        {'id': C},
    ]
    rows = asyncio.run(fetch_genres(client, [A, B, A, C], captured))
    assert [call.args[0] for call in client.get.await_args_list] == [f'/artists/{A}', f'/artists/{B}', f'/artists/{C}']
    assert [(r.spotify_artist_id, r.genres) for r in rows] == [(A, ['j-pop', 'anime']), (B, [])]
    assert rows[0].captured_at == captured


def test_unrequested_artist_is_rejected():
    client = AsyncMock()
    client.get.return_value = {'id': B, 'genres': ['j-pop']}
    with pytest.raises(ValueError):
        asyncio.run(fetch_genres(client, [A], datetime.now(UTC)))


def test_transient_failures_retry_and_missing_artists_are_skipped():
    client = AsyncMock()
    client.get.side_effect = [
        SpotifyFailure('provider_error', retry=True),
        {'id': A, 'genres': ['anime']},
        SpotifyFailure('provider_error'),  # 404: no longer served
    ]
    sleep = AsyncMock()
    rows = asyncio.run(fetch_genres(client, [A, B], datetime.now(UTC), sleep=sleep))
    assert [(r.spotify_artist_id, r.genres) for r in rows] == [(A, ['anime'])]
    assert sleep.await_count == 1


def test_retry_limit_stops_the_run():
    client = AsyncMock()
    client.get.side_effect = SpotifyFailure('rate_limited', retry=True, retry_after=1)
    with pytest.raises(SpotifyFailure):
        asyncio.run(fetch_genres(client, [A], datetime.now(UTC), retries=2, sleep=AsyncMock()))
    assert client.get.await_count == 3


def test_normalize_caps_length_and_rejects_non_lists():
    assert normalize_genres('j-pop') is None
    assert len(normalize_genres([f'g{i}' for i in range(30)])) == 20


def test_artist_read_defaults_to_no_genres():
    artist = ArtistRead(id=1, name='x')
    assert artist.spotify_genres == [] and artist.spotify_genres_updated_at is None
    assert ArtistRead(id=1, name='x', spotify_genres=['j-pop']).spotify_genres == ['j-pop']
