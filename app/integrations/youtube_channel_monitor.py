from __future__ import annotations

import logging
import re
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.artist_identity import artist_name_aliases
from app.core.db import RIOT_MUSIC_YOUTUBE_CHANNELS, get_connection
from app.integrations.youtube_context import YOUTUBE_API_BASE_URL
from app.integrations.youtube_live_archive import add_youtube_live_url


logger = logging.getLogger(__name__)
CHANNEL_ID_RE = re.compile(r"^UC[\w-]{20,}$")
VESPERBELL_ARTIST_NAME = "VESPERBELL"
VESPERBELL_YOMI_ARTIST_NAME = "VESPERBELL YOMI"
VESPERBELL_KASUKA_ARTIST_NAME = "VESPERBELL KASUKA"
KMNZ_ARTIST_NAME = "KMNZ"
KMNZ_LITA_ARTIST_NAME = "KMNZ LITA"
KMNZ_NERO_ARTIST_NAME = "KMNZ NERO"
KMNZ_TINA_ARTIST_NAME = "KMNZ TINA"
SINGING_STREAM_TITLE_KEYWORDS = (
    "\u6b4c\u67a0",
    "\u6b4c\u914d\u4fe1",
    "\u30ab\u30e9\u30aa\u30b1",
    "\u5f3e\u304d\u8a9e\u308a",
    "\u3046\u305f\u308f\u304f",
    "singing",
    "singing stream",
    "karaoke",
    "karaoke stream",
    "acoustic",
    "閭뚧옞",
    "?먩춯?졼",
)
COVER_VIDEO_KEYWORDS = ("cover", "歌ってみた", "歌唱", "カバー", "covered by")


def _is_singing_stream_title(title: str) -> bool:
    normalized = title.casefold()
    return any(keyword.casefold() in normalized for keyword in SINGING_STREAM_TITLE_KEYWORDS)


def _is_cover_video(title: str, description: str = "") -> bool:
    text = f"{title}\n{description}".casefold()
    return any(keyword.casefold() in text for keyword in COVER_VIDEO_KEYWORDS)


def _channel_locator(channel_url: str) -> tuple[str, str]:
    parsed = urlparse(channel_url.strip())
    if (parsed.hostname or "").lower() not in {
        "youtube.com", "www.youtube.com", "m.youtube.com"
    }:
        raise ValueError("youtube.com 채널 URL을 입력해 주세요.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "channel" and CHANNEL_ID_RE.match(parts[1]):
        return "id", parts[1]
    if parts and parts[0].startswith("@") and len(parts[0]) > 1:
        return "handle", parts[0][1:]
    raise ValueError("/@handle 또는 /channel/UC... 형식의 채널 URL을 입력해 주세요.")


async def resolve_youtube_channel(channel_url: str) -> dict[str, str]:
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY가 설정되지 않았습니다.")
    locator_type, locator = _channel_locator(channel_url)
    params = {
        "part": "snippet,contentDetails",
        "key": settings.youtube_api_key,
        "id" if locator_type == "id" else "forHandle": locator,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{YOUTUBE_API_BASE_URL}/channels", params=params)
        response.raise_for_status()
        items = response.json().get("items") or []
    if not items:
        raise ValueError("YouTube 채널을 찾을 수 없습니다.")
    item = items[0]
    uploads = (((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
    if not uploads:
        raise ValueError("채널의 업로드 목록을 찾을 수 없습니다.")
    return {
        "youtube_channel_id": item["id"],
        "channel_title": (item.get("snippet") or {}).get("title") or locator,
        "channel_url": f"https://www.youtube.com/channel/{item['id']}",
        "uploads_playlist_id": uploads,
    }


async def create_youtube_channel_monitor(
    *, discord_user_id: str, artist_name: str, channel_url: str
) -> dict[str, Any]:
    channel = await resolve_youtube_channel(channel_url)
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO youtube_channel_monitors (
                discord_user_id, artist_name, youtube_channel_id, channel_title,
                channel_url, uploads_playlist_id
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (discord_user_id, youtube_channel_id) DO UPDATE SET
                artist_name = EXCLUDED.artist_name,
                channel_title = EXCLUDED.channel_title,
                channel_url = EXCLUDED.channel_url,
                uploads_playlist_id = EXCLUDED.uploads_playlist_id,
                is_active = TRUE,
                next_check_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (
                discord_user_id, artist_name.strip(), channel["youtube_channel_id"],
                channel["channel_title"], channel["channel_url"],
                channel["uploads_playlist_id"],
            ),
        ).fetchone()
        conn.commit()
        return row


def list_youtube_channel_monitors(discord_user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return conn.execute(
            """SELECT * FROM youtube_channel_monitors
               WHERE discord_user_id = %s ORDER BY artist_name, id""",
            (discord_user_id,),
        ).fetchall()


def delete_youtube_channel_monitor(monitor_id: int, discord_user_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM youtube_channel_monitors WHERE id = %s AND discord_user_id = %s",
            (monitor_id, discord_user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


async def poll_youtube_channel_monitors(
    *, monitor_id: int | None = None, limit: int = 25
) -> dict[str, int]:
    if not settings.youtube_api_key:
        return {"channels_checked": 0, "videos_found": 0, "archives_created": 0, "covers_saved": 0}
    with get_connection() as conn:
        monitors = conn.execute(
            """
            SELECT * FROM youtube_channel_monitors
            WHERE is_active = TRUE
              AND (%s::integer IS NULL OR id = %s)
              AND (%s::integer IS NOT NULL OR next_check_at <= CURRENT_TIMESTAMP)
            ORDER BY next_check_at, id LIMIT %s
            """,
            (monitor_id, monitor_id, monitor_id, limit),
        ).fetchall()

    result = {"channels_checked": 0, "videos_found": 0, "archives_created": 0, "covers_saved": 0}
    for monitor in monitors:
        try:
            videos = await _fetch_recent_singing_streams(monitor["uploads_playlist_id"])
            # Routine polling checks the newest uploads. Historical imports use
            # ``backfill_youtube_covers`` and deliberately traverse everything.
            covers = await _fetch_recent_cover_videos(monitor["uploads_playlist_id"], max_videos=200)
            result["channels_checked"] += 1
            result["videos_found"] += len(videos)
            result["covers_saved"] += _upsert_cover_videos(monitor["artist_name"], covers)
            _upsert_channel_videos(monitor["id"], videos)
            result["archives_created"] += await _collect_due_videos(monitor)
            _mark_monitor_checked(monitor["id"])
        except Exception as exc:
            logger.exception("YouTube channel monitor #%s failed", monitor["id"])
            _mark_monitor_checked(monitor["id"], error=str(exc))
    return result


async def backfill_youtube_covers(*, monitor_id: int | None = None) -> dict[str, int]:
    """Import the complete cover catalogue for registered official channels."""
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured.")
    with get_connection() as conn:
        monitors = conn.execute(
            """SELECT id, artist_name, uploads_playlist_id FROM youtube_channel_monitors
               WHERE is_active = TRUE AND (%s::integer IS NULL OR id = %s)
               ORDER BY id""",
            (monitor_id, monitor_id),
        ).fetchall()
    result = {"channels_checked": 0, "covers_saved": 0, "failed": 0}
    for monitor in monitors:
        try:
            covers = await _fetch_recent_cover_videos(monitor["uploads_playlist_id"])
            result["channels_checked"] += 1
            result["covers_saved"] += _upsert_cover_videos(monitor["artist_name"], covers)
        except Exception:
            result["failed"] += 1
            logger.exception("YouTube cover import failed for channel monitor #%s", monitor["id"])
    return result


async def _fetch_recent_cover_videos(
    uploads_playlist_id: str,
    *,
    max_videos: int | None = None,
) -> list[dict[str, Any]]:
    """Return every upload whose title or description identifies it as a cover."""
    candidates: list[str] = []
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "part": "snippet,contentDetails", "playlistId": uploads_playlist_id,
                "maxResults": "50", "key": settings.youtube_api_key,
            }
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(f"{YOUTUBE_API_BASE_URL}/playlistItems", params=params)
            response.raise_for_status()
            payload = response.json()
            candidates.extend(
                (item.get("contentDetails") or {}).get("videoId")
                for item in payload.get("items") or []
                if (item.get("contentDetails") or {}).get("videoId")
            )
            if max_videos is not None and len(candidates) >= max_videos:
                candidates = candidates[:max_videos]
                break
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        items: list[dict[str, Any]] = []
        for index in range(0, len(candidates), 50):
            response = await client.get(
                f"{YOUTUBE_API_BASE_URL}/videos",
                params={"part": "snippet,liveStreamingDetails", "id": ",".join(candidates[index:index + 50]), "key": settings.youtube_api_key},
            )
            response.raise_for_status()
            items.extend(response.json().get("items") or [])
    covers = []
    for item in items:
        snippet = item.get("snippet") or {}
        title = snippet.get("title") or ""
        description = snippet.get("description") or ""
        # A singing live archive can contain cover keywords in its description,
        # but this catalogue is intentionally only for normal video uploads.
        if not (item.get("liveStreamingDetails") or {}).get("actualStartTime") and _is_cover_video(title, description):
            covers.append({
                "youtube_video_id": item["id"], "video_title": title,
                "video_description": description,
                "published_at": _parse_datetime(snippet.get("publishedAt")),
            })
    return covers


def _upsert_cover_videos(artist_name: str, covers: list[dict[str, Any]]) -> int:
    """Store covers only when the monitor can be tied to one registered artist."""
    if not covers:
        return 0
    with get_connection() as conn:
        artist = conn.execute(
            "SELECT id FROM artists WHERE LOWER(name) = LOWER(%s) OR LOWER(COALESCE(display_name, '')) = LOWER(%s) LIMIT 1",
            (artist_name, artist_name),
        ).fetchone()
        if artist is None:
            return 0
        for cover in covers:
            row = conn.execute(
                """
                INSERT INTO youtube_cover_videos (
                    artist_id, youtube_video_id, youtube_url, video_title, video_description, published_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (artist_id, youtube_video_id) DO UPDATE SET
                    video_title = EXCLUDED.video_title,
                    video_description = EXCLUDED.video_description,
                    published_at = COALESCE(EXCLUDED.published_at, youtube_cover_videos.published_at),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (artist["id"], cover["youtube_video_id"], f"https://www.youtube.com/watch?v={cover['youtube_video_id']}",
                 cover["video_title"], cover["video_description"], cover["published_at"]),
            )
            cover_row = conn.execute("SELECT id FROM youtube_cover_videos WHERE artist_id = %s AND youtube_video_id = %s", (artist["id"], cover["youtube_video_id"])).fetchone()
            conn.execute("DELETE FROM youtube_cover_collaborators WHERE cover_id = %s", (cover_row["id"],))
            text = f"{cover['video_title']}\n{cover['video_description']}".casefold()
            candidates = conn.execute("SELECT id, name, display_name FROM artists WHERE id <> %s", (artist["id"],)).fetchall()
            for candidate in candidates:
                aliases = artist_name_aliases(candidate["name"]) + ([candidate["display_name"]] if candidate["display_name"] else [])
                if any(alias and len(alias) >= 3 and alias.casefold() in text for alias in aliases):
                    conn.execute("INSERT INTO youtube_cover_collaborators (cover_id, artist_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (cover_row["id"], candidate["id"]))
        conn.commit()
    return len(covers)


async def _fetch_recent_singing_streams(
    uploads_playlist_id: str,
    *,
    max_videos: int | None = None,
) -> list[dict[str, Any]]:
    """Return completed live archives whose title identifies them as an utawaku.

    The uploads playlist is paginated at 50 items by YouTube.  A channel
    monitor must therefore follow ``nextPageToken``; otherwise older archives
    silently never enter the setlist collection pipeline.
    """
    candidates: list[dict[str, str]] = []
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "part": "snippet,contentDetails", "playlistId": uploads_playlist_id,
                "maxResults": "50", "key": settings.youtube_api_key,
            }
            if page_token:
                params["pageToken"] = page_token
            playlist_response = await client.get(
                f"{YOUTUBE_API_BASE_URL}/playlistItems", params=params
            )
            playlist_response.raise_for_status()
            payload = playlist_response.json()
            candidates.extend(
                {
                    "id": (item.get("contentDetails") or {}).get("videoId"),
                    "title": (item.get("snippet") or {}).get("title") or "",
                }
                for item in payload.get("items") or []
                if _is_singing_stream_title((item.get("snippet") or {}).get("title") or "")
            )
            if max_videos is not None and len(candidates) >= max_videos:
                candidates = candidates[:max_videos]
                break
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        ids = [item["id"] for item in candidates if item["id"]]
        if not ids:
            return []
        video_items: list[dict[str, Any]] = []
        for index in range(0, len(ids), 50):
            videos_response = await client.get(
                f"{YOUTUBE_API_BASE_URL}/videos",
                params={
                    "part": "snippet,liveStreamingDetails", "id": ",".join(ids[index:index + 50]),
                    "key": settings.youtube_api_key,
                },
            )
            videos_response.raise_for_status()
            video_items.extend(videos_response.json().get("items") or [])
    return [
        {
            "youtube_video_id": item["id"],
            "video_title": (item.get("snippet") or {}).get("title") or "",
            "actual_end_at": _parse_datetime(
                (item.get("liveStreamingDetails") or {}).get("actualEndTime")
            ),
        }
        for item in video_items
        # Titles also match Shorts and ordinary uploads. Require evidence of
        # both an actual broadcast and its completion, excluding scheduled
        # and currently live videos as well.
        if (item.get("liveStreamingDetails") or {}).get("actualStartTime")
        and (item.get("liveStreamingDetails") or {}).get("actualEndTime")
    ]


def _performer_for_singing_stream(default_artist_name: str, video_title: str) -> str:
    """Map supported group stream-title member tags to their artist records.

    VESPERBELL also uses collaboration tags such as ``#ヨミネロ``.  Any title
    that includes a member's name belongs to that member, even when a
    collaborator's name follows it.  Streams without either member name
    remain attributed to the duo itself.
    """
    if default_artist_name.casefold() == VESPERBELL_ARTIST_NAME.casefold():
        if "ヨミ" in video_title:
            return VESPERBELL_YOMI_ARTIST_NAME
        if "カスカ" in video_title:
            return VESPERBELL_KASUKA_ARTIST_NAME
        return VESPERBELL_ARTIST_NAME

    if default_artist_name.casefold() == KMNZ_ARTIST_NAME.casefold():
        # 모든 멤버 태그에 그룹 접두사가 있으므로 일반 #KMNZ 태그보다
        # 개별 멤버 태그를 먼저 확인합니다.
        normalized_title = video_title.upper()
        if "#KMNZLITA" in normalized_title:
            return KMNZ_LITA_ARTIST_NAME
        if "#KMNZNERO" in normalized_title:
            return KMNZ_NERO_ARTIST_NAME
        if "#KMNZTINA" in normalized_title:
            return KMNZ_TINA_ARTIST_NAME
        return KMNZ_ARTIST_NAME

    return default_artist_name


async def backfill_youtube_channel(
    *,
    channel_url: str,
    artist_name: str,
    max_videos: int | None = None,
    concurrency: int = 1,
) -> dict[str, int]:
    """Store all historical utawaku archives for one artist.

    The archive insertion is idempotent by YouTube video ID, so the operation
    is safe to rerun after comments are updated or a collection run fails.
    """
    channel = await resolve_youtube_channel(channel_url)
    videos = await _fetch_recent_singing_streams(
        channel["uploads_playlist_id"],
        max_videos=max_videos,
    )
    with get_connection() as conn:
        existing_ids = {
            row["youtube_video_id"]
            for row in conn.execute(
                "SELECT youtube_video_id FROM youtube_live_archives "
                "WHERE youtube_video_id = ANY(%s)",
                ([video["youtube_video_id"] for video in videos],),
            ).fetchall()
        }
    videos = [video for video in videos if video["youtube_video_id"] not in existing_ids]
    async def store(video: dict[str, Any]) -> tuple[bool, bool]:
        try:
            archive_id = await add_youtube_live_url(
                f"https://www.youtube.com/watch?v={video['youtube_video_id']}",
                _performer_for_singing_stream(artist_name, video["video_title"]),
                enrich_karaoke=False,
            )
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT jsonb_array_length(setlist) AS song_count "
                    "FROM youtube_live_archives WHERE id = %s",
                    (archive_id,),
                ).fetchone()
            return True, bool(row and row["song_count"])
        except Exception:
            # HTTP 요청 URL에는 쿼리 문자열의 API 키가 포함되므로 일반 작업
            # 로그에 기록하지 않습니다.
            logger.warning("YouTube historical backfill failed for video %s", video["youtube_video_id"])
            return False, False

    semaphore = asyncio.Semaphore(max(1, min(concurrency, 10)))

    async def limited_store(video: dict[str, Any]) -> tuple[bool, bool]:
        async with semaphore:
            return await store(video)

    outcomes = await asyncio.gather(*(limited_store(video) for video in videos))
    result = {
        "videos_found": len(videos),
        "archives_saved": sum(saved for saved, _ in outcomes),
        "setlists_found": sum(found for _, found in outcomes),
        "failed": sum(not saved for saved, _ in outcomes),
    }
    return result


async def create_riot_music_youtube_channel_monitors(
    *, discord_user_id: str
) -> dict[str, Any]:
    """Register official RIOT MUSIC artist channels for one Discord user."""
    monitors = []
    failed: list[dict[str, str]] = []
    for artist_name, channel_url in RIOT_MUSIC_YOUTUBE_CHANNELS:
        try:
            monitors.append(
                await create_youtube_channel_monitor(
                    discord_user_id=discord_user_id,
                    artist_name=artist_name,
                    channel_url=channel_url,
                )
            )
        except Exception as exc:
            logger.exception("RIOT MUSIC YouTube monitor seed failed for %s", artist_name)
            failed.append({"artist_name": artist_name, "error": str(exc)})
    return {
        "requested": len(RIOT_MUSIC_YOUTUBE_CHANNELS),
        "registered": len(monitors),
        "failed": failed,
        "monitors": monitors,
    }


async def backfill_riot_music_youtube_channels(
    *, max_videos_per_channel: int | None = None, concurrency: int = 3
) -> dict[str, Any]:
    """Store historical RIOT MUSIC utawaku archives from official channels."""
    channels: list[dict[str, Any]] = []
    totals = {
        "channels_checked": 0,
        "videos_found": 0,
        "archives_saved": 0,
        "setlists_found": 0,
        "failed": 0,
    }
    for artist_name, channel_url in RIOT_MUSIC_YOUTUBE_CHANNELS:
        try:
            result = await backfill_youtube_channel(
                channel_url=channel_url,
                artist_name=artist_name,
                max_videos=max_videos_per_channel,
                concurrency=concurrency,
            )
            totals["channels_checked"] += 1
            for key in ("videos_found", "archives_saved", "setlists_found", "failed"):
                totals[key] += int(result[key])
            channels.append({"artist_name": artist_name, **result})
        except Exception as exc:
            logger.exception("RIOT MUSIC YouTube backfill failed for %s", artist_name)
            totals["failed"] += 1
            channels.append({"artist_name": artist_name, "error": str(exc)})
    return {**totals, "channels": channels}


def _upsert_channel_videos(monitor_id: int, videos: list[dict[str, Any]]) -> None:
    with get_connection() as conn:
        for video in videos:
            end_at = video["actual_end_at"]
            conn.execute(
                """
                INSERT INTO youtube_channel_videos (
                    monitor_id, youtube_video_id, video_title, actual_end_at, collect_after
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (monitor_id, youtube_video_id) DO UPDATE SET
                    video_title = EXCLUDED.video_title,
                    actual_end_at = COALESCE(EXCLUDED.actual_end_at, youtube_channel_videos.actual_end_at),
                    collect_after = COALESCE(EXCLUDED.collect_after, youtube_channel_videos.collect_after),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    monitor_id, video["youtube_video_id"], video["video_title"],
                    end_at, end_at + timedelta(hours=24) if end_at else None,
                ),
            )
        conn.commit()


async def _collect_due_videos(monitor: dict[str, Any]) -> int:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, youtube_video_id, video_title FROM youtube_channel_videos
            WHERE monitor_id = %s AND status <> 'processed'
              AND collect_after IS NOT NULL AND collect_after <= CURRENT_TIMESTAMP
            ORDER BY collect_after, id
            """,
            (monitor["id"],),
        ).fetchall()
    processed = 0
    for row in rows:
        try:
            archive_id = await add_youtube_live_url(
                f"https://www.youtube.com/watch?v={row['youtube_video_id']}",
                _performer_for_singing_stream(monitor["artist_name"], row["video_title"]),
            )
            with get_connection() as conn:
                conn.execute(
                    """UPDATE youtube_channel_videos SET status = 'processed', archive_id = %s,
                       last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                    (archive_id, row["id"]),
                )
                conn.commit()
            processed += 1
        except Exception as exc:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE youtube_channel_videos SET status = 'retry', last_error = %s,
                       updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                    (str(exc)[:1000], row["id"]),
                )
                conn.commit()
    return processed


def _mark_monitor_checked(monitor_id: int, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE youtube_channel_monitors SET last_checked_at = CURRENT_TIMESTAMP,
               next_check_at = CURRENT_TIMESTAMP + INTERVAL '1 day',
               updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
            (monitor_id,),
        )
        conn.commit()
