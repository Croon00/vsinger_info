from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from psycopg import errors

from app.core.config import settings
from app.core.db import get_connection, init_db
from app.integrations.google_calendar import (
    create_calendar_events,
    get_calendar_recipients_for_source,
)
from app.integrations.notifications import (
    find_notification_routes_for_item,
    record_notification_delivery,
    update_source_item_classification,
)
from app.integrations.web_pages import fetch_public_page_text
from app.integrations.x_client import fetch_recent_posts, get_x_user_id, post_url, x_configured
from app.integrations.jpop_playlist_tj import apply_jpop_playlist_matches, refresh_jpop_playlist_index_if_stale
from app.integrations.youtube_live_archive import (
    refresh_pending_youtube_lives,
    register_youtube_live,
)
from app.integrations.youtube_channel_monitor import poll_youtube_channel_monitors
from app.lyrics_pipeline.youtube import extract_youtube_video_id

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


async def run_agent_once() -> dict[str, int]:
    """등록된 X 출처를 한 번 순회하며 새 게시물, 일정 후보, 캘린더 등록을 처리합니다."""
    if settings.database_auto_init:
        init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.artist_id,
                s.value AS x_username,
                s.external_user_id,
                s.last_seen_external_id,
                a.name AS artist_name,
                a.discord_user_id
            FROM artist_sources s
            JOIN artists a ON a.id = s.artist_id
            WHERE s.is_active = TRUE
                AND s.source_type = 'x'
                AND a.discord_user_id IS NOT NULL
            ORDER BY s.id
            """
        ).fetchall()

    result = {
        "active_x_sources": len(rows),
        "posts_seen": 0,
        "posts_classified": 0,
        "events_created": 0,
        "calendar_events_created": 0,
        "notifications_sent": 0,
        "notifications_skipped": 0,
        "youtube_live_archives_updated": 0,
        "youtube_channels_checked": 0,
        "youtube_channel_archives_created": 0,
        "youtube_covers_saved": 0,
        "jpop_playlist_rows_loaded": 0,
        "jpop_playlist_performances_updated": 0,
    }
    playlist_result = await _refresh_jpop_playlist_safely()
    result["jpop_playlist_rows_loaded"] = playlist_result["rows_loaded"]
    result["jpop_playlist_performances_updated"] = playlist_result["performances_updated"]
    if not rows or not x_configured():
        result["youtube_live_archives_updated"] = (
            await _refresh_youtube_live_archives_safely()
        )
        channel_result = await _poll_youtube_channels_safely()
        result["youtube_channels_checked"] = channel_result["channels_checked"]
        result["youtube_channel_archives_created"] = channel_result["archives_created"]
        result["youtube_covers_saved"] = channel_result.get("covers_saved", 0)
        return result

    for source in rows:
        try:
            source_result = await _process_x_source(source)
            for key, value in source_result.items():
                result[key] += value
        except Exception:
            logger.exception("출처 %s 처리 중 agent가 실패했습니다.", source["id"])

    result["youtube_live_archives_updated"] = (
        await _refresh_youtube_live_archives_safely()
    )
    channel_result = await _poll_youtube_channels_safely()
    result["youtube_channels_checked"] = channel_result["channels_checked"]
    result["youtube_channel_archives_created"] = channel_result["archives_created"]
    result["youtube_covers_saved"] = channel_result.get("covers_saved", 0)
    return result


async def _poll_youtube_channels_safely() -> dict[str, int]:
    try:
        return await poll_youtube_channel_monitors()
    except Exception:
        logger.exception("YouTube channel monitor polling failed.")
        return {"channels_checked": 0, "videos_found": 0, "archives_created": 0, "covers_saved": 0}


async def _refresh_jpop_playlist_safely() -> dict[str, int]:
    """Refresh the public TJ index weekly, then apply safe cached matches."""
    try:
        loaded = await refresh_jpop_playlist_index_if_stale()
        return {"rows_loaded": loaded, "performances_updated": apply_jpop_playlist_matches()}
    except Exception:
        logger.exception("J-POP Playlist TJ refresh failed.")
        return {"rows_loaded": 0, "performances_updated": 0}


async def _process_x_source(source: dict[str, Any]) -> dict[str, int]:
    """아티스트의 X 계정 하나를 처리해서 새 게시물을 읽고 일정으로 변환합니다."""
    x_username = source["x_username"]
    x_user_id = source["external_user_id"] or await get_x_user_id(x_username)
    if not source["external_user_id"]:
        _update_source_x_user_id(source["id"], x_user_id)

    posts = await fetch_recent_posts(x_user_id, source["last_seen_external_id"])
    posts = sorted(posts, key=lambda post: int(post["id"]))
    result = {
        "posts_seen": len(posts),
        "posts_classified": 0,
        "events_created": 0,
        "calendar_events_created": 0,
        "notifications_sent": 0,
        "notifications_skipped": 0,
    }

    newest_post_id = source["last_seen_external_id"]
    for post in posts:
        newest_post_id = post["id"]
        source_item_id = _insert_source_item(source, post)
        if source_item_id is None:
            continue

        item_type = "notice"
        update_source_item_classification(
            source_item_id=source_item_id,
            item_type=item_type,
            confidence=None,
        )

        _register_youtube_live_links(
            source_item_id=source_item_id,
            source_id=source["id"],
            post=post,
        )

        notification_result = await _notify_discord_routes(
            source=source,
            post=post,
            source_item_id=source_item_id,
            item_type=item_type,
            classification_reason=None,
            event=None,
        )
        result["notifications_sent"] += notification_result["sent"]
        result["notifications_skipped"] += notification_result["skipped"]

    if newest_post_id:
        _update_last_seen(source["id"], newest_post_id)

    return result


def _update_source_x_user_id(source_id: int, x_user_id: str) -> None:
    """X username으로 조회한 X 내부 user id를 source row에 저장합니다."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE artist_sources SET external_user_id = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (x_user_id, source_id),
        )
        conn.commit()


def _update_last_seen(source_id: int, post_id: str) -> None:
    """다음 agent 실행 때 중복으로 읽지 않도록 마지막으로 본 X 게시물 ID를 저장합니다."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE artist_sources
            SET last_seen_external_id = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (post_id, source_id),
        )
        conn.commit()


def _insert_source_item(source: dict[str, Any], post: dict[str, Any]) -> int | None:
    """X 게시물을 source_items에 저장하고 새 row id를 반환합니다.

    이미 저장된 게시물이면 None을 반환합니다. 반환된 row id는 분류 결과를
    같은 source_items row에 업데이트하는 데 사용합니다.
    """
    published_at = _parse_datetime(post.get("created_at"))
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO source_items (
                    discord_user_id, source_id, external_id, url, published_at, raw_text
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    source["discord_user_id"],
                    source["id"],
                    post["id"],
                    post_url(source["x_username"], post["id"]),
                    published_at,
                    post["text"],
                ),
            )
            source_item_id = cursor.fetchone()["id"]
            conn.commit()
            return int(source_item_id)
        except errors.UniqueViolation:
            conn.rollback()
            return None


def _insert_event_candidate(
    source: dict[str, Any],
    post: dict[str, Any],
    extracted: dict[str, Any],
    raw_text: str,
    item_type: str,
) -> tuple[dict[str, Any], bool]:
    """AI가 추출한 공연/예매 정보를 일정 후보 테이블에 저장합니다."""
    with get_connection() as conn:
        event_type = item_type if item_type in {"live_event", "ticket"} else "live_event"
        existing = conn.execute(
            """SELECT * FROM event_candidates
               WHERE event_type = %s
                 AND COALESCE(starts_at, '') = COALESCE(%s, '')
                 AND regexp_replace(lower(title), '[^[:alnum:]]', '', 'g') = %s
               ORDER BY id LIMIT 1""",
            (event_type, extracted.get("starts_at"), _event_title_key(extracted["title"])),
        ).fetchone()
        if existing:
            return existing, False
        cursor = conn.execute(
            """
            INSERT INTO event_candidates (
                artist_id, discord_user_id, source_id, event_type, event_format, title, starts_at, venue,
                ticket_opens_at, ticket_closes_at, ticket_url, price_text,
                source_url, raw_text, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ready')
            RETURNING *
            """,
            (
                source["artist_id"],
                source["discord_user_id"],
                source["id"],
                event_type,
                extracted.get("event_format", "unknown"),
                extracted["title"],
                extracted.get("starts_at"),
                extracted.get("venue"),
                extracted.get("ticket_opens_at"),
                extracted.get("ticket_closes_at"),
                extracted.get("ticket_url"),
                extracted.get("price_text"),
                post_url(source["x_username"], post["id"]),
                raw_text,
            ),
        )
        event = cursor.fetchone()
        conn.commit()
        return event, True


def _event_title_key(title: str) -> str:
    """Stable event identity across reposts with harmless punctuation differences."""
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", title).casefold())


def _calendar_sync_types(discord_user_id: str, event_candidate_id: int) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT event_type FROM calendar_syncs
               WHERE discord_user_id = %s AND event_candidate_id = %s AND provider = 'google'""",
            (discord_user_id, event_candidate_id),
        ).fetchall()
    return {str(row["event_type"]) for row in rows}


def _insert_calendar_sync(
    discord_user_id: str,
    event_candidate_id: int,
    provider_event_id: str,
    event_type: str = "live",
) -> None:
    """Google Calendar에 생성한 event ID를 저장해 중복 등록을 추적합니다."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO calendar_syncs (
                discord_user_id, event_candidate_id, provider_event_id, event_type
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (discord_user_id, event_candidate_id, provider, event_type) DO NOTHING
            """,
            (discord_user_id, event_candidate_id, provider_event_id, event_type),
        )
        conn.commit()


async def _notify_discord_routes(
    *,
    source: dict[str, Any],
    post: dict[str, Any],
    source_item_id: int | None = None,
    item_type: str,
    classification_reason: str | None,
    event: dict[str, Any] | None,
) -> dict[str, int]:
    """Send a classified item to every active Discord route for this source/type.

    The agent can also be run from a CLI or tests without a logged-in Discord bot.
    In that case this function skips delivery instead of waiting forever.
    """
    routes = find_notification_routes_for_item(source_id=source["id"])
    if not routes:
        return {"sent": 0, "skipped": 0}

    try:
        from app.bots.discord_bot import bot
    except Exception:
        logger.exception("Discord bot import failed while sending notifications.")
        return {"sent": 0, "skipped": len(routes)}

    if bot.is_closed() or not bot.is_ready():
        logger.info("Discord bot is not ready; skipped %s route notifications.", len(routes))
        return {"sent": 0, "skipped": len(routes)}

    message = _build_notification_message(
        source=source,
        post=post,
        item_type=item_type,
        classification_reason=classification_reason,
        event=event,
    )
    sent = 0
    skipped = 0
    for route in routes:
        channel = bot.get_channel(int(route["discord_channel_id"]))
        if channel is None or not hasattr(channel, "send"):
            skipped += 1
            continue
        try:
            discord_message = await channel.send(message)
            if source_item_id is not None:
                record_notification_delivery(
                    route_id=int(route["id"]),
                    source_item_id=source_item_id,
                    discord_message_id=str(discord_message.id),
                )
            sent += 1
        except Exception:
            skipped += 1
            logger.exception("Discord route %s notification failed.", route["id"])
    return {"sent": sent, "skipped": skipped}


def _build_notification_message(
    *,
    source: dict[str, Any],
    post: dict[str, Any],
    item_type: str,
    classification_reason: str | None,
    event: dict[str, Any] | None,
) -> str:
    """Build a short Discord message for one classified source item."""
    labels = {
        "notice": "공지",
        "release": "음악",
        "live_event": "!!라이브 정보",
        "ticket": "티켓",
        "merch": "굿즈",
        "irrelevant": "잡담",
    }
    url = post_url(source["x_username"], post["id"])
    if item_type == "live_event" and _youtube_urls(post):
        return f"{source['artist_name']} (분류: 유튜브 라이브)\n{url}"
    if item_type in {"live_event", "ticket"}:
        return (
            f"{source['artist_name']} "
            f"(\ubd84\ub958: [!!\ub77c\uc774\ube0c \uc815\ubcf4])\n{url}"
        )
    label = "!!라이브 정보" if item_type in {"live_event", "ticket"} else labels.get(item_type, item_type)
    # URL만 포함하면 Discord가 X 미리보기 카드 하나를 렌더링합니다. 원문 본문을
    # 반복하지 않아 원문 안의 링크가 추가 embed를 만들지 않습니다.
    return f"{source['artist_name']} (분류: {label})\n{url}"


def _first_line(value: str) -> str:
    """Return the first non-empty line for compact notification titles."""
    for line in value.splitlines():
        stripped = line.strip()
        if stripped:
            return _truncate_text(stripped, 160)
    return "새 글"


def _truncate_text(value: str, max_chars: int) -> str:
    """Keep Discord messages safely under the 2000 character limit."""
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 1].rstrip() + "…"


async def _fetch_post_page_context(post: dict[str, Any]) -> str | None:
    urls = _extract_post_urls(post)
    if not urls:
        return None

    chunks = []
    for url in urls[:3]:
        text = await fetch_public_page_text(url)
        if text:
            chunks.append(f"URL: {url}\n{text}")
    return "\n\n".join(chunks) if chunks else None


def _extract_post_urls(post: dict[str, Any]) -> list[str]:
    urls = []
    for item in (post.get("entities") or {}).get("urls") or []:
        url = item.get("expanded_url") or item.get("unwound_url") or item.get("url")
        if not url or url in urls:
            continue
        hostname = (urlparse(url).hostname or "").lower()
        # X 페이지는 게시물과 프로필 소개를 함께 반복합니다. 소개에 "release"나
        # "EP"가 있으면 일반 대화가 발매 공지처럼 분류될 수 있어 이를 제거합니다.
        if hostname in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            continue
        urls.append(url)
    return urls


def _youtube_urls(post: dict[str, Any]) -> list[str]:
    """Return linked YouTube URLs from an X post."""
    youtube_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }
    return [
        url
        for url in _extract_post_urls(post)
        if (urlparse(url).hostname or "").lower() in youtube_hosts
    ]


def _register_youtube_live_links(
    *,
    source_item_id: int,
    source_id: int,
    post: dict[str, Any],
) -> None:
    """Queue linked YouTube lives for post-stream setlist collection."""
    for url in _youtube_urls(post):
        try:
            video_id = extract_youtube_video_id(url)
        except ValueError:
            logger.info("YouTube video ID를 찾지 못해 기록을 건너뜁니다: %s", url)
            continue
        register_youtube_live(
            source_item_id=source_item_id,
            source_id=source_id,
            youtube_video_id=video_id,
            youtube_url=url,
        )


async def _refresh_youtube_live_archives_safely() -> int:
    """Refresh archives without allowing YouTube failures to stop X polling."""
    try:
        return await refresh_pending_youtube_lives()
    except Exception:
        logger.exception("YouTube live archive refresh failed.")
        return 0


def _combine_raw_text(post_text: str, page_context: str | None) -> str:
    if not page_context:
        return post_text
    return f"{post_text}\n\n--- Linked page context ---\n{page_context}"


def _normalize_ticket_open_from_post(post: dict[str, Any], extracted: dict[str, Any]) -> None:
    """Use the post timestamp when a ticket-start announcement lacks a clear date."""
    ticket_opens_at = extracted.get("ticket_opens_at")
    published_at = _parse_datetime(post.get("created_at"))
    if not ticket_opens_at or not published_at:
        return

    parsed_ticket_opens_at = _parse_datetime(ticket_opens_at)
    if parsed_ticket_opens_at and parsed_ticket_opens_at.tzinfo is None:
        parsed_ticket_opens_at = parsed_ticket_opens_at.replace(tzinfo=timezone.utc)
    if parsed_ticket_opens_at and parsed_ticket_opens_at < published_at:
        extracted["ticket_opens_at"] = published_at.astimezone(JST).isoformat()


def _normalize_live_date_from_post(post: dict[str, Any], extracted: dict[str, Any]) -> None:
    """Resolve yearless and relative live dates against the source post timestamp."""
    if not extracted.get("is_live_event"):
        return

    published_at = _parse_datetime(post.get("created_at"))
    if not published_at:
        return

    text = unicodedata.normalize("NFKC", post.get("text", ""))
    date_match = re.search(
        r"(?<!\d)(1[0-2]|0?[1-9])\s*[./月]\s*(3[01]|[12]\d|0?[1-9])(?:日)?(?!\d)",
        text,
    )
    is_today = bool(re.search(r"(?:本日|今日|today|오늘)", text, re.IGNORECASE))
    if not date_match and not is_today:
        return

    local_published = published_at.astimezone(JST)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = local_published.year
        if (month, day) < (local_published.month, local_published.day):
            year += 1
    else:
        year, month, day = local_published.year, local_published.month, local_published.day

    time_match = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*[:：]\s*([0-5]\d)", text)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        extracted["starts_at"] = datetime(year, month, day, hour, minute, tzinfo=JST).isoformat()
    else:
        extracted["starts_at"] = f"{year:04d}-{month:02d}-{day:02d}"


def _parse_datetime(value: str | None) -> datetime | None:
    """X API의 ISO 문자열 시간을 Python datetime으로 변환합니다."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def agent_loop() -> None:
    """Railway 프로세스가 살아 있는 동안 설정된 주기마다 agent를 반복 실행합니다."""
    if not settings.agent_run_on_start:
        await asyncio.sleep(settings.agent_interval_seconds)

    while True:
        try:
            result = await run_agent_once()
            logger.info("agent 실행 완료: %s", result)
        except Exception:
            logger.exception("agent 실행에 실패했습니다.")

        await asyncio.sleep(settings.agent_interval_seconds)
