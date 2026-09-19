"""YouTube 라이브 아카이브 유스케이스를 제공한다."""

from typing import Any

from app.core.db import get_connection

from app.integrations.youtube_channel_monitor import backfill_youtube_channel
from app.integrations.youtube_live_archive import (
    add_youtube_live_url,
    ensure_youtube_live_korean_labels,
    get_youtube_live_archive,
    list_youtube_live_archives,
    list_youtube_performance_filters,
    search_youtube_song_performances,
    update_youtube_song_performance,
    list_youtube_performance_stats,
)


class YouTubeService:
    """YouTube 수집 연동을 API 유스케이스로 감싼다."""

    async def create_live(self, youtube_url: str, artist_name: str) -> dict[str, Any] | None:
        """YouTube 라이브 URL을 저장하고 세트리스트 수집을 시도한다."""
        archive_id = await add_youtube_live_url(youtube_url, artist_name)
        return get_youtube_live_archive(archive_id)

    async def backfill_channel(self, channel_url: str, artist_name: str) -> dict[str, int]:
        """채널의 과거 라이브를 수집한다."""
        return await backfill_youtube_channel(channel_url=channel_url, artist_name=artist_name)

    def list_lives(self, limit: int, artist_name: str | None, all_records: bool = False) -> list[dict[str, Any]]:
        """저장된 YouTube 라이브 목록을 조회한다."""
        artist_name = (artist_name or '').strip() or None
        return list_youtube_live_archives(limit=None if all_records and artist_name else max(1, min(limit, 100)), artist_name=artist_name)

    async def get_live(self, archive_id: int) -> dict[str, Any] | None:
        """한국어 메타데이터를 보완한 라이브 상세 정보를 조회한다."""
        await ensure_youtube_live_korean_labels(archive_id)
        return get_youtube_live_archive(archive_id)

    def search_performances(self, **filters: Any) -> list[dict[str, Any]]:
        """곡명·가수명 조건으로 라이브 공연 기록을 검색한다."""
        return search_youtube_song_performances(**filters)

    def list_performance_filters(self) -> dict[str, list[str]]:
        """공연 검색 필터 후보를 반환한다."""
        return list_youtube_performance_filters()

    def list_performance_stats(self, group_by: str) -> list[dict[str, Any]]:
        return list_youtube_performance_stats(group_by)

    def update_performance(self, performance_id: int, values: dict[str, str | None]) -> dict[str, Any] | None:
        """공연 곡 정보를 수정한다."""
        return update_youtube_song_performance(performance_id, values)

    def list_covers(self, artist_id: int | None = None, collaborator_id: int | None = None, limit: int = 500) -> list[dict[str, Any]]:
        """List collected official-channel cover uploads, newest first."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.artist_id, COALESCE(a.display_name, a.name) AS artist_name,
                       c.youtube_video_id, c.youtube_url, c.video_title, c.video_description,
                       c.published_at
                FROM youtube_cover_videos c
                JOIN artists a ON a.id = c.artist_id
                WHERE (%s::integer IS NULL OR c.artist_id = %s)
                  AND (%s::integer IS NULL OR EXISTS (SELECT 1 FROM youtube_cover_collaborators cc WHERE cc.cover_id = c.id AND cc.artist_id = %s))
                ORDER BY c.published_at DESC NULLS LAST, c.id DESC
                LIMIT %s
                """,
                (artist_id, artist_id, collaborator_id, collaborator_id, max(1, min(limit, 1000))),
            ).fetchall()
            if not rows:
                return []
            participants = conn.execute(
                """SELECT cc.cover_id, a.id, COALESCE(a.display_name, a.name) AS name
                   FROM youtube_cover_collaborators cc JOIN artists a ON a.id = cc.artist_id
                   WHERE cc.cover_id = ANY(%s) ORDER BY a.name""",
                ([row["id"] for row in rows],),
            ).fetchall()
            by_cover: dict[int, list[dict[str, Any]]] = {row["id"]: [] for row in rows}
            for participant in participants:
                by_cover[participant["cover_id"]].append({"id": participant["id"], "name": participant["name"]})
            return [{**row, "collaborators": by_cover[row["id"]]} for row in rows]
            
