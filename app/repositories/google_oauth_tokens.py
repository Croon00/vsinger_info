from datetime import UTC, datetime, timedelta
from typing import Any

from app.legacy.config import settings
from app.core.db import get_connection


def get_token(discord_user_id: str) -> dict[str, Any] | None:
    """Discord 사용자에 저장된 Google OAuth 토큰을 조회한다."""
    with get_connection() as conn:
        return conn.execute("SELECT * FROM google_oauth_tokens WHERE discord_user_id = %s", (discord_user_id,)).fetchone()


def save_token(discord_user_id: str, token: dict[str, Any]) -> None:
    """Google OAuth 응답을 사용자별로 upsert하고 만료 시각을 계산한다."""
    expires_at = datetime.now(UTC) + timedelta(seconds=int(token["expires_in"])) if token.get("expires_in") else None
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO google_oauth_tokens (discord_user_id, access_token, refresh_token, expires_at, scope, token_type, calendar_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (discord_user_id) DO UPDATE SET access_token = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, google_oauth_tokens.refresh_token), expires_at = EXCLUDED.expires_at,
                scope = EXCLUDED.scope, token_type = EXCLUDED.token_type, calendar_id = EXCLUDED.calendar_id, updated_at = CURRENT_TIMESTAMP
        """, (discord_user_id, token["access_token"], token.get("refresh_token"), expires_at, token.get("scope"), token.get("token_type"), settings.google_calendar_id))
        conn.commit()


def calendar_recipients(source_id: int, source_owner_id: str) -> list[str]:
    """소스 소유자와 알림 라우트 중 Calendar가 연결된 수신자를 반환한다."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT recipients.discord_user_id FROM (
                SELECT %s AS discord_user_id UNION SELECT r.discord_user_id FROM notification_routes r
                WHERE r.is_active = TRUE AND (r.source_id = %s OR r.source_id IS NULL) AND r.discord_user_id IS NOT NULL
            ) recipients JOIN google_oauth_tokens tokens ON tokens.discord_user_id = recipients.discord_user_id
            ORDER BY recipients.discord_user_id
        """, (source_owner_id, source_id)).fetchall()
    return [str(row["discord_user_id"]) for row in rows]
