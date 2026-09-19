"""TJ lookup using the public J-POP Playlist karaoke-number tables.

The source is fetched only when a refresh is explicitly requested.  Rows are
matched conservatively: an exact normalized title must have one TJ number, or
the source artist must also match the setlist's original artist.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from app.core.db import get_connection


SOURCE_NAME = "j-pop-playlist.tistory.com"
SOURCE_BASE_URL = "https://j-pop-playlist.tistory.com"
CATEGORY_PATH = (
    "/category/%EB%85%B8%EB%9E%98%EB%B0%A9%20%EB%B2%88%ED%98%B8/"
    "J-POP%20%EB%85%B8%EB%9E%98%EB%B0%A9%20%EB%B2%88%ED%98%B8"
)
USER_AGENT = "schedule-music/1.0 (karaoke number lookup)"


@dataclass(frozen=True)
class PlaylistSong:
    title: str
    artist: str | None
    tj_number: str
    source_url: str


def normalize_karaoke_text(value: str | None) -> str:
    """Normalize safe title/artist variants without doing fuzzy matching."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[\s\-‐‑‒–—―_·・:：'\"“”‘’()\[\]{}!！?？.,，。/\\]+", "", value)
    return value


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


class _TableParser(HTMLParser):
    """Small dependency-free table parser for Tistory post markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_playlist_songs(html: str, source_url: str) -> list[PlaylistSong]:
    """Extract rows shaped as title, TJ, KY, JOYSOUND/artist from a post."""
    parser = _TableParser()
    parser.feed(html)
    songs: list[PlaylistSong] = []
    for row in parser.rows:
        if len(row) < 3:
            continue
        title = _first_line(row[0])
        tj_number = _first_line(row[1])
        if not title or not re.fullmatch(r"\d{3,8}", tj_number):
            continue
        last_column = _first_line(row[3]) if len(row) >= 4 else ""
        # Most artist pages use the fourth column for JOYSOUND, whereas some
        # compilation pages use it for an artist.  A number is never an
        # artist, so do not accidentally treat the JOYSOUND value as one.
        artist = None if re.fullmatch(r"-|\d{3,8}", last_column) else last_column
        songs.append(PlaylistSong(title, artist or None, tj_number, source_url))
    return songs


def _post_urls(category_html: str) -> set[str]:
    return {
        urljoin(SOURCE_BASE_URL, f"/{post_id}")
        for post_id in re.findall(r'''href=["']/(\d+)["']''', category_html)
    }


async def refresh_jpop_playlist_index(
    *, max_pages: int = 20, page_delay_seconds: float = 0.25, max_posts: int | None = None
) -> int:
    """Fetch the J-POP category and upsert its explicitly listed TJ numbers."""
    post_urls: set[str] = set()
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            response = await client.get(f"{SOURCE_BASE_URL}{CATEGORY_PATH}", params={"page": page})
            response.raise_for_status()
            post_urls.update(_post_urls(response.text))
            await asyncio.sleep(page_delay_seconds)

        async def fetch_post(post_url: str) -> list[PlaylistSong]:
            response = await client.get(post_url)
            response.raise_for_status()
            return parse_playlist_songs(response.text, post_url)

        songs: list[PlaylistSong] = []
        post_url_list = sorted(post_urls)
        if max_posts is not None:
            post_url_list = post_url_list[:max_posts]
        # Four requests at a time keeps this one-off import practical while
        # staying well below aggressive crawler behaviour.
        for start in range(0, len(post_url_list), 4):
            songs.extend(
                song
                for batch in await asyncio.gather(
                    *(fetch_post(url) for url in post_url_list[start : start + 4])
                )
                for song in batch
            )
            await asyncio.sleep(page_delay_seconds)

    rows = [
        (song.title, song.artist, song.tj_number, song.source_url, SOURCE_NAME)
        for song in songs
    ]
    if not rows:
        return 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO karaoke_source_matches
                    (song_title, artist_name, tj_number, source_url, source_name)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_name, song_title, artist_name, tj_number) DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        conn.commit()
    return len(rows)


async def refresh_jpop_playlist_index_if_stale(max_age_days: int = 7) -> int:
    """Refresh the public index at most once per period for new TJ entries."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT MAX(fetched_at) AS fetched_at FROM karaoke_source_matches
               WHERE source_name = %s""",
            (SOURCE_NAME,),
        ).fetchone()
    if row and row["fetched_at"] is not None:
        from datetime import datetime, timedelta, timezone

        if row["fetched_at"] >= datetime.now(timezone.utc) - timedelta(days=max_age_days):
            return 0
    return await refresh_jpop_playlist_index()


def apply_jpop_playlist_matches() -> int:
    """Write unambiguous cached TJ matches to performances still without a number."""
    with get_connection() as conn:
        source_rows = conn.execute(
            "SELECT song_title, artist_name, tj_number FROM karaoke_source_matches WHERE source_name = %s",
            (SOURCE_NAME,),
        ).fetchall()
        performances = conn.execute(
            """
            SELECT id, song_title, original_artist
            FROM youtube_song_performances
            WHERE tj_number !~ '^[0-9]'
            """
        ).fetchall()

        by_title: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in source_rows:
            title_key = normalize_karaoke_text(row["song_title"])
            if title_key:
                by_title[title_key].append((normalize_karaoke_text(row["artist_name"]), row["tj_number"]))

        updates: list[tuple[str, int]] = []
        for row in performances:
            candidates = by_title.get(normalize_karaoke_text(row["song_title"]), [])
            artist_key = normalize_karaoke_text(row["original_artist"])
            if artist_key:
                artist_numbers = {number for artist, number in candidates if artist == artist_key}
                if len(artist_numbers) == 1:
                    updates.append((next(iter(artist_numbers)), row["id"]))
                continue
            numbers = {number for _, number in candidates}
            if len(numbers) == 1:
                updates.append((next(iter(numbers)), row["id"]))

        if updates:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE youtube_song_performances
                    SET tj_number = %s, karaoke_checked_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tj_number !~ '^[0-9]'
                    """,
                    updates,
                )
        conn.commit()
    return len(updates)


def cached_jpop_playlist_matches(
    songs: list[tuple[str, str | None]],
) -> dict[int, PlaylistSong]:
    """Return only unambiguous TJ matches already imported from J-POP Playlist."""
    if not songs:
        return {}
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT song_title, artist_name, tj_number, source_url
               FROM karaoke_source_matches WHERE source_name = %s""",
            (SOURCE_NAME,),
        ).fetchall()
    by_title: dict[str, list[PlaylistSong]] = defaultdict(list)
    for row in rows:
        key = normalize_karaoke_text(row["song_title"])
        if key:
            by_title[key].append(
                PlaylistSong(row["song_title"], row["artist_name"], row["tj_number"], row["source_url"])
            )

    matches: dict[int, PlaylistSong] = {}
    for index, (title, original_artist) in enumerate(songs):
        candidates = by_title.get(normalize_karaoke_text(title), [])
        artist_key = normalize_karaoke_text(original_artist)
        if artist_key:
            candidates = [song for song in candidates if normalize_karaoke_text(song.artist) == artist_key]
        numbers = {song.tj_number for song in candidates}
        if len(numbers) == 1 and candidates:
            matches[index] = candidates[0]
    return matches
