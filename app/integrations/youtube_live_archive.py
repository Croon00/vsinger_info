from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from psycopg.types.json import Jsonb

from app.core.config import settings
from app.core.db import get_connection
from app.core.artist_identity import artist_name_aliases, display_artist_name
from app.integrations.youtube_context import fetch_setlist_comment, fetch_video_metadata
from app.integrations.karaoke_lookup import lookup_karaoke_numbers, split_song_credit
from app.integrations.spotify_title_translation import (
    translate_japanese_artist_names,
    translate_japanese_titles,
)
from app.lyrics_pipeline.youtube import canonical_youtube_watch_url, extract_youtube_video_id


logger = logging.getLogger(__name__)
TIMESTAMP_LINE_RE = re.compile(
    r"(?<!\d)(?P<timestamp>(?:\d{1,2}:)?\d{1,2}:\d{2})(?!\d)"
    r"(?:\s*[-–—|｜:：.]?\s*)"
    r"(?P<title>.+?)\s*$"
)
SETLIST_RANGE_END_RE = re.compile(
    r"^\s*[~〜～\-–—]\s*(?:\d{1,2}:)?[0-5]?\d:[0-5]\d\s*"
)
SETLIST_SCORE_SUFFIX_RE = re.compile(
    r"\s+[0-9０-９]+(?:[.．][0-9０-９]+)?(?:点|pts?\.?)?\s*$",
    re.IGNORECASE,
)
SETLIST_QUOTED_SONG_RE = re.compile(r'[「『"](?P<song>.+?)[」』"]')
MAX_ARCHIVE_ATTEMPTS = 168
SETLIST_TITLE_PREFIX_RE = re.compile(
    r"^(?:#\s*)?(?:제\s*)?\d+\s*(?:곡목?|曲目?)?\s*(?:[.．:：\-—)]\s*)+",
    re.IGNORECASE,
)
SETLIST_TIMESTAMP_PREFIX_RE = re.compile(
    r"^(?:(?:\d{1,2}:){1,2}\d{1,2})(?:\s+|[-–—|｜:：.]\s*)"
)
TIMESTAMP_ONLY_TITLE_RE = re.compile(
    r"^(?:(?:\d{1,2}:){1,2}\d{1,2})(?:\s+(?:(?:\d{1,2}:){1,2}\d{1,2}))*$"
)
LEADING_SETLIST_DECORATION_RE = re.compile(r"^[\s、，,・•●▶▷►♪♫☆★◇◆□■【】<>＜＞「」『』|｜:：\-–—]+")
LEADING_TIMESTAMP_NOISE_RE = re.compile(
    r"^[\s\W_]+(?=(?:\d{1,2}:){1,2}\d{1,2}(?:\s|[-–—|｜:：.]|$))",
    re.UNICODE,
)
NUMBERED_HASH_PREFIX_RE = re.compile(r"^[#＃]\s*\d{1,3}\s*(?:[.．、:：\-–—)]\s*)*")
DOUBLE_SETLIST_INDEX_PREFIX_RE = re.compile(
    r"^\d{1,3}\s+[#＃]\s*\d{1,3}\s*(?:[.．、:：\-–—)]\s*)*"
)
TRAILING_TIMESTAMP_RE = re.compile(r"\s+(?:(?:\d{1,2}:){1,2}\d{1,2})$")
NON_SONG_ATTENDEE_LABEL_RE = re.compile(r"^@\s*\d+\s*人\s*$")


def register_youtube_live(
    *,
    source_item_id: int,
    source_id: int,
    youtube_video_id: str,
    youtube_url: str,
) -> None:
    """Register a YouTube live so its post-stream setlist can be collected."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO youtube_live_archives (
                source_item_id, source_id, youtube_video_id, youtube_url
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_item_id, youtube_video_id) DO NOTHING
            """,
            (source_item_id, source_id, youtube_video_id, youtube_url),
        )
        conn.commit()


def _normalise_match_text(value: str | None) -> str:
    """Compare Japanese/Roman titles without whitespace or punctuation noise."""
    return re.sub(r"[\s\W_]", "", (value or "").casefold())


def _apply_korean_metadata(archive_id: int) -> None:
    """Fill Korean labels from the saved song library, without overwriting edits."""
    with get_connection() as conn:
        performances = conn.execute(
            """SELECT id, song_title, original_artist, song_title_ko, original_artist_ko
               FROM youtube_song_performances WHERE archive_id = %s""",
            (archive_id,),
        ).fetchall()


        songs = conn.execute(
            """SELECT original_title, title_ko, artist_name, artist_name_ko
               FROM songs WHERE title_ko IS NOT NULL OR artist_name_ko IS NOT NULL"""
        ).fetchall()
        for performance in performances:
            title_key = _normalise_match_text(performance["song_title"])
            artist_key = _normalise_match_text(performance["original_artist"])
            matches = [song for song in songs if _normalise_match_text(song["original_title"]) == title_key]
            if artist_key:
                artist_matches = [song for song in matches if _normalise_match_text(song["artist_name"]) == artist_key]
                if artist_matches:
                    matches = artist_matches
            if len(matches) != 1:
                continue
            song = matches[0]
            conn.execute(
                """UPDATE youtube_song_performances
                   SET song_title_ko = COALESCE(song_title_ko, %s),
                       original_artist_ko = COALESCE(original_artist_ko, %s)
                   WHERE id = %s""",
                (song["title_ko"], song["artist_name_ko"], performance["id"]),
            )
        conn.commit()


async def _translate_korean_song_titles(archive_id: int) -> None:
    """Fill missing Korean setlist titles once, while preserving manual edits."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, song_title
            FROM youtube_song_performances
            WHERE archive_id = %s AND song_title_ko IS NULL
            ORDER BY start_seconds, id
            """,
            (archive_id,),
        ).fetchall()
    if not rows:
        return
    try:
        translations = await translate_japanese_titles(
            [(str(row["id"]), row["song_title"]) for row in rows]
        )
    except Exception:
        logger.exception("Setlist title translation failed for archive #%s.", archive_id)
        return
    if not translations:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE youtube_song_performances
                SET song_title_ko = %s
                WHERE id = %s AND song_title_ko IS NULL
                """,
                [
                    (title_ko, int(performance_id))
                    for performance_id, title_ko in translations.items()
                ],
            )
        conn.commit()


async def _translate_korean_original_artists(archive_id: int) -> None:
    """Fill Korean original-artist labels once and keep manual labels intact."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, original_artist
            FROM youtube_song_performances
            WHERE archive_id = %s
              AND original_artist IS NOT NULL
              AND original_artist_ko IS NULL
            ORDER BY start_seconds, id
            """,
            (archive_id,),
        ).fetchall()
    if not rows:
        return
    try:
        translations = await translate_japanese_artist_names(
            [(str(row["id"]), row["original_artist"]) for row in rows]
        )
    except Exception:
        logger.exception("Setlist artist-name translation failed for archive #%s.", archive_id)
        return
    if not translations:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE youtube_song_performances
                SET original_artist_ko = %s
                WHERE id = %s AND original_artist_ko IS NULL
                """,
                [(name_ko, int(performance_id)) for performance_id, name_ko in translations.items()],
            )
        conn.commit()


async def ensure_youtube_live_korean_labels(archive_id: int) -> None:
    """Backfill Korean setlist labels when an older archive is opened."""
    _apply_korean_metadata(archive_id)
    await _translate_korean_song_titles(archive_id)
    await _translate_korean_original_artists(archive_id)


def update_youtube_song_performance(performance_id: int, values: dict[str, str | None]) -> dict[str, Any] | None:
    allowed = {"song_title", "song_title_ko", "original_artist", "original_artist_ko"}
    updates = {key: value.strip() if isinstance(value, str) and value.strip() else None for key, value in values.items() if key in allowed}
    if not updates:
        return None
    if "song_title" in updates and updates["song_title"] is None:
        raise ValueError("곡 제목은 비워둘 수 없습니다.")
    assignments = ", ".join(f"{key} = %s" for key in updates)
    with get_connection() as conn:
        row = conn.execute(
            f"""UPDATE youtube_song_performances SET {assignments}
                WHERE id = %s
                RETURNING id, performed_on, start_seconds, timestamp_text, song_title, song_title_ko,
                          original_artist, original_artist_ko, tj_number, ky_number, karaoke_checked_at""",
            (*updates.values(), performance_id),
        ).fetchone()
        conn.commit()
        return row


async def add_youtube_live_url(
    youtube_url: str,
    artist_name: str | None = None,
    *,
    enrich_karaoke: bool = True,
) -> int:
    """Register a URL directly and immediately collect its dated setlist."""
    video_id = extract_youtube_video_id(youtube_url)
    canonical_url = canonical_youtube_watch_url(youtube_url)
    metadata = await fetch_video_metadata(video_id)
    try:
        context = await fetch_setlist_comment(video_id)
    except httpx.HTTPStatusError as exc:
        # 공개 archive라도 댓글이 비활성화될 수 있습니다. 채널 backfill 전체를
        # 실패시키는 대신 날짜와 영상 링크를 대기 기록으로 보존합니다.
        logger.info("Comments unavailable for YouTube video %s: %s", video_id, exc.response.status_code)
        context = None
    comment = context.text if context else None
    setlist = parse_setlist_comment(comment or "")

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM youtube_live_archives WHERE youtube_video_id = %s ORDER BY id LIMIT 1",
            (video_id,),
        ).fetchone()
        values = (
            canonical_url,
            artist_name.strip() if artist_name else None,
            metadata.title if metadata else None,
            metadata.published_at if metadata else None,
            metadata.broadcast_at if metadata else None,
            "ready" if setlist else "pending",
            comment,
            Jsonb(setlist),
        )
        if existing:
            conn.execute(
                """
                UPDATE youtube_live_archives SET youtube_url = %s,
                    performer_name = COALESCE(%s, performer_name),
                    video_title = COALESCE(%s, video_title),
                    published_at = COALESCE(%s, published_at),
                    broadcast_at = COALESCE(%s, broadcast_at), status = %s,
                    top_comment = COALESCE(%s, top_comment), setlist = %s,
                    attempts = attempts + 1, last_checked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (*values, existing["id"]),
            )
            archive_id = existing["id"]
        else:
            row = conn.execute(
                """
                INSERT INTO youtube_live_archives (
                    youtube_video_id, youtube_url, performer_name, video_title, published_at,
                    broadcast_at, status, top_comment, setlist, attempts,
                    last_checked_at, next_check_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '1 hour')
                RETURNING id
                """,
                (video_id, *values),
            ).fetchone()
            archive_id = row["id"]
        conn.commit()
    _replace_song_performances(archive_id, setlist)
    await _translate_korean_song_titles(archive_id)
    if enrich_karaoke:
        await _enrich_karaoke_numbers(archive_id)
    await _translate_korean_original_artists(archive_id)
    return int(archive_id)


def parse_setlist_comment(text: str) -> list[dict[str, str]]:
    """Extract timestamp/song pairs, retaining only song title and artist credit."""
    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        match = TIMESTAMP_LINE_RE.search(line)
        if not match:
            continue
        title = _normalise_setlist_song(match.group("title"))
        if not title or re.match(r"^start(?:\b|[：:\-])", title, re.IGNORECASE):
            continue
        entries.append(
            {
                "timestamp": match.group("timestamp"),
                "title": title,
            }
        )
    return entries


def _normalise_setlist_song(value: str) -> str:
    """Remove range endpoints, scores, labels, and quote wrappers from a song row."""
    cleaned = SETLIST_TITLE_PREFIX_RE.sub("", value.strip())
    cleaned = SETLIST_RANGE_END_RE.sub("", cleaned)
    quoted = SETLIST_QUOTED_SONG_RE.search(cleaned)
    if quoted:
        cleaned = quoted.group("song")
    cleaned = SETLIST_SCORE_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned.replace("／", "/").replace("｜", "/")


async def refresh_pending_youtube_lives(limit: int = 10) -> int:
    """Check due YouTube lives and store a timestamped top-comment setlist."""
    if not settings.youtube_api_key:
        return 0

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, youtube_video_id
            FROM youtube_live_archives
            WHERE status = 'pending'
                AND attempts < %s
                AND next_check_at <= CURRENT_TIMESTAMP
            ORDER BY next_check_at, id
            LIMIT %s
            """,
            (MAX_ARCHIVE_ATTEMPTS, limit),
        ).fetchall()

    updated = 0
    for row in rows:
        try:
            metadata = await fetch_video_metadata(row["youtube_video_id"])
            context = await fetch_setlist_comment(row["youtube_video_id"])
            comment = context.text if context else None
            setlist = parse_setlist_comment(comment or "")
            await _save_check_result(
                archive_id=row["id"],
                comment=comment,
                setlist=setlist,
                metadata=metadata,
            )
            if setlist:
                await _enrich_karaoke_numbers(row["id"])
                updated += 1
        except Exception:
            logger.exception(
                "YouTube live archive #%s comment check failed.",
                row["id"],
            )
            await _save_check_result(
                archive_id=row["id"],
                comment=None,
                setlist=[],
                metadata=None,
            )
    return updated


async def _save_check_result(
    *,
    archive_id: int,
    comment: str | None,
    setlist: list[dict[str, str]],
    metadata: Any | None,
    translate_titles: bool = True,
) -> None:
    status = "ready" if setlist else "pending"
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE youtube_live_archives
            SET
                status = %s,
                top_comment = COALESCE(%s, top_comment),
                setlist = %s,
                video_title = COALESCE(%s, video_title),
                published_at = COALESCE(%s, published_at),
                broadcast_at = COALESCE(%s, broadcast_at),
                attempts = attempts + 1,
                last_checked_at = CURRENT_TIMESTAMP,
                next_check_at = CURRENT_TIMESTAMP + INTERVAL '1 hour',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                status, comment, Jsonb(setlist),
                metadata.title if metadata else None,
                metadata.published_at if metadata else None,
                metadata.broadcast_at if metadata else None,
                archive_id,
            ),
        )
        conn.commit()
    if setlist:
        _replace_song_performances(archive_id, setlist)
        if translate_titles:
            await _translate_korean_song_titles(archive_id)


def _timestamp_to_seconds(timestamp: str) -> int:
    parts = [int(part) for part in timestamp.split(":")]
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def _replace_song_performances(
    archive_id: int,
    setlist: list[dict[str, str]],
) -> None:
    """Store searchable per-song rows using the stream date in Japan time."""
    with get_connection() as conn:
        performed_on = conn.execute(
            """
            SELECT COALESCE(broadcast_at, published_at) AT TIME ZONE 'Asia/Tokyo' AS local_at
            FROM youtube_live_archives WHERE id = %s
            """,
            (archive_id,),
        ).fetchone()["local_at"]
        if performed_on is None:
            return
        conn.execute(
            "DELETE FROM youtube_song_performances WHERE archive_id = %s",
            (archive_id,),
        )
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO youtube_song_performances (
                    archive_id, performed_on, start_seconds, timestamp_text, song_title, original_artist
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        archive_id,
                        performed_on.date(),
                        _timestamp_to_seconds(entry["timestamp"]),
                        entry["timestamp"],
                        split_song_credit(entry["title"])[0],
                        split_song_credit(entry["title"])[1] or None,
                    )
                    for entry in setlist
                ],
            )
        conn.commit()
    _apply_korean_metadata(archive_id)


async def _enrich_karaoke_numbers(archive_id: int) -> None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, song_title, original_artist FROM youtube_song_performances
            WHERE archive_id = %s ORDER BY start_seconds, id
            """,
            (archive_id,),
        ).fetchall()
    if not rows:
        return
    # 원본 세트리스트에 크레딧이 있으면 아티스트 정보를 복구합니다.
    with get_connection() as conn:
        raw_setlist = conn.execute(
            "SELECT setlist FROM youtube_live_archives WHERE id = %s", (archive_id,)
        ).fetchone()["setlist"]
    songs = [split_song_credit(entry["title"]) for entry in raw_setlist]
    matches = await lookup_karaoke_numbers(songs)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE youtube_song_performances SET original_artist = %s,
                    tj_number = %s, ky_number = %s, karaoke_checked_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                [
                    (match.original_artist, match.tj_number, match.ky_number, row["id"])
                    for row, match in zip(rows, matches, strict=False)
                ],
            )
        conn.commit()
    _apply_korean_metadata(archive_id)
    await _translate_korean_original_artists(archive_id)


def list_youtube_live_archives(limit: int | None = 20, artist_name: str | None = None) -> list[dict[str, Any]]:
    """Return recent YouTube live archives with artist and X-post context."""
    with get_connection() as conn:
        archives = conn.execute(
            """
            SELECT
                y.id,
                y.youtube_url,
                y.status,
                y.setlist,
                y.video_title,
                y.published_at,
                y.broadcast_at,
                y.last_checked_at,
                COALESCE(a.name, y.performer_name, y.video_title, 'YouTube') AS artist_name,
                si.url AS x_post_url
            FROM youtube_live_archives y
            LEFT JOIN artist_sources s ON s.id = y.source_id
            LEFT JOIN artists a ON a.id = s.artist_id
            LEFT JOIN source_items si ON si.id = y.source_item_id
            WHERE (%s::text IS NULL OR COALESCE(a.name, y.performer_name, '') ILIKE '%%' || %s || '%%'
                OR LOWER(COALESCE(a.name, y.performer_name, '')) = ANY(%s))
              AND (y.duration_seconds IS NULL OR y.duration_seconds > 420)
            ORDER BY COALESCE(y.broadcast_at, y.published_at) DESC NULLS LAST, y.id DESC
            LIMIT %s
            """,
            (artist_name, artist_name, [alias.lower() for alias in artist_name_aliases(artist_name)] if artist_name else [], limit),
        ).fetchall()
        if not archives:
            return archives
        for archive in archives:
            archive['artist_name'] = display_artist_name(archive['artist_name'])
        archive_ids = [archive["id"] for archive in archives]
        performances = conn.execute(
            """
            SELECT id, archive_id, performed_on, start_seconds, timestamp_text, song_title,
                   song_title_ko, original_artist, original_artist_ko, tj_number, ky_number,
                   karaoke_checked_at
            FROM youtube_song_performances
            WHERE archive_id = ANY(%s)
            ORDER BY archive_id, start_seconds, id
            """,
            (archive_ids,),
        ).fetchall()
    by_archive_id: dict[int, list[dict[str, Any]]] = {}
    for performance in performances:
        by_archive_id.setdefault(performance["archive_id"], []).append(performance)
    for archive in archives:
        archive["performances"] = by_archive_id.get(archive["id"], [])
    return archives


def get_youtube_live_archive(archive_id: int) -> dict[str, Any] | None:
    """Return one archived live and its parsed setlist."""
    _apply_korean_metadata(archive_id)
    with get_connection() as conn:
        archive = conn.execute(
            """
            SELECT
                y.*,
                COALESCE(a.name, y.performer_name, y.video_title, 'YouTube') AS artist_name,
                si.url AS x_post_url
            FROM youtube_live_archives y
            LEFT JOIN artist_sources s ON s.id = y.source_id
            LEFT JOIN artists a ON a.id = s.artist_id
            LEFT JOIN source_items si ON si.id = y.source_item_id
            WHERE y.id = %s
            """,
            (archive_id,),
        ).fetchone()
        if archive is None:
            return None
        archive['artist_name'] = display_artist_name(archive['artist_name'])
        archive["performances"] = conn.execute(
            """
            SELECT id, performed_on, start_seconds, timestamp_text, song_title, song_title_ko,
                   original_artist, original_artist_ko, tj_number, ky_number, karaoke_checked_at
            FROM youtube_song_performances WHERE archive_id = %s
            ORDER BY start_seconds, id
            """,
            (archive_id,),
        ).fetchall()
        return archive


def search_youtube_song_performances(
    *,
    artist_names: list[str] | None = None,
    song_titles: list[str] | None = None,
    original_artists: list[str] | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Search archived performances using OR matching within each selected filter."""
    performer_patterns = list(dict.fromkeys(f"%{alias}%" for value in artist_names or [] if value.strip()
                                           for alias in artist_name_aliases(value.strip())))
    song_patterns = [f"%{value.strip()}%" for value in song_titles or [] if value.strip()]
    original_artist_patterns = [f"%{value.strip()}%" for value in original_artists or [] if value.strip()]

    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                p.id,
                p.archive_id,
                p.performed_on,
                p.start_seconds,
                p.timestamp_text,
                p.song_title,
                p.song_title_ko,
                p.original_artist,
                p.original_artist_ko,
                p.tj_number,
                p.ky_number,
                y.youtube_url,
                y.video_title,
                COALESCE(a.name, y.performer_name, y.video_title, 'YouTube') AS artist_name
            FROM youtube_song_performances p
            JOIN youtube_live_archives y ON y.id = p.archive_id
            LEFT JOIN artist_sources s ON s.id = y.source_id
            LEFT JOIN artists a ON a.id = s.artist_id
            WHERE (%s::text[] = ARRAY[]::text[] OR COALESCE(a.name, y.performer_name, '') ILIKE ANY(%s))
              AND (y.duration_seconds IS NULL OR y.duration_seconds > 420)
              AND (
                %s::text[] = ARRAY[]::text[]
                OR p.song_title ILIKE ANY(%s)
                OR COALESCE(p.song_title_ko, '') ILIKE ANY(%s)
              )
              AND (
                %s::text[] = ARRAY[]::text[]
                OR COALESCE(p.original_artist, '') ILIKE ANY(%s)
                OR COALESCE(p.original_artist_ko, '') ILIKE ANY(%s)
              )
            ORDER BY p.performed_on DESC, p.start_seconds, p.id
            LIMIT %s
            """,
            (
                performer_patterns, performer_patterns,
                song_patterns, song_patterns, song_patterns,
                original_artist_patterns, original_artist_patterns, original_artist_patterns,
                max(1, min(limit, 500)),
            ),
        ).fetchall()


def list_youtube_performance_stats(group_by: str, limit: int = 200) -> list[dict[str, Any]]:
    field = "p.song_title" if group_by == "song" else "p.original_artist"
    korean = "MAX(NULLIF(p.song_title_ko, ''))" if group_by == "song" else "MAX(NULLIF(p.original_artist_ko, ''))"
    with get_connection() as conn:
        return conn.execute(f"""SELECT {field} AS label, {korean} AS korean_label, COUNT(*)::integer AS count
            FROM youtube_song_performances p JOIN youtube_live_archives y ON y.id = p.archive_id
            WHERE {field} IS NOT NULL AND {field} <> '' AND (y.duration_seconds IS NULL OR y.duration_seconds > 420)
            GROUP BY {field} ORDER BY count DESC, label LIMIT %s""", (max(1, min(limit, 500)),)).fetchall()


def list_youtube_performance_filters(limit: int = 500) -> dict[str, list[str]]:
    """Return distinct values used by the multi-select performance search UI."""
    with get_connection() as conn:
        performers = conn.execute(
            """SELECT DISTINCT COALESCE(a.name, y.performer_name) AS value
               FROM youtube_song_performances p JOIN youtube_live_archives y ON y.id = p.archive_id
               LEFT JOIN artist_sources s ON s.id = y.source_id LEFT JOIN artists a ON a.id = s.artist_id
               WHERE COALESCE(a.name, y.performer_name) IS NOT NULL ORDER BY value LIMIT %s""",
            (limit,),
        ).fetchall()
        original_artists = conn.execute(
            """
            SELECT DISTINCT value FROM (
                SELECT original_artist AS value FROM youtube_song_performances
                UNION
                SELECT original_artist_ko AS value FROM youtube_song_performances
            ) names
            WHERE value IS NOT NULL AND value <> ''
            ORDER BY value LIMIT %s
            """,
            (limit,),
        ).fetchall()
        songs = conn.execute(
            """
            SELECT DISTINCT value FROM (
                SELECT song_title AS value FROM youtube_song_performances
                UNION
                SELECT song_title_ko AS value FROM youtube_song_performances
            ) titles
            WHERE value IS NOT NULL AND value <> ''
            ORDER BY value LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"performers": sorted({display_artist_name(row['value']) for row in performers}), "original_artists": [row["value"] for row in original_artists], "songs": [row["value"] for row in songs]}
