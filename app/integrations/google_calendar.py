from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.legacy.config import settings
from app.repositories.google_oauth_tokens import calendar_recipients, get_token, save_token


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def google_oauth_configured() -> bool:
    """Google OAuth에 필요한 client id, secret, redirect uri가 모두 있는지 확인합니다."""
    return bool(
        settings.google_client_id
        and settings.google_client_secret
        and get_google_redirect_uri()
    )


def get_google_redirect_uri() -> str | None:
    """명시된 redirect uri가 있으면 쓰고, 없으면 PUBLIC_BASE_URL로 callback 주소를 만듭니다."""
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    if settings.public_base_url:
        return f"{settings.public_base_url.rstrip('/')}/auth/google/callback"
    return None


def build_google_auth_url(discord_user_id: str) -> str:
    """Discord 사용자 ID를 state에 담은 Google Calendar 권한 요청 URL을 만듭니다."""
    redirect_uri = get_google_redirect_uri()
    if not settings.google_client_id or not redirect_uri:
        raise RuntimeError("Google OAuth가 설정되어 있지 않습니다.")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": discord_user_id,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str, discord_user_id: str) -> None:
    """Google callback으로 받은 code를 access/refresh token으로 교환해 DB에 저장합니다."""
    redirect_uri = get_google_redirect_uri()
    if not settings.google_client_id or not settings.google_client_secret or not redirect_uri:
        raise RuntimeError("Google OAuth가 설정되어 있지 않습니다.")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        token = response.json()

    _store_google_token(discord_user_id, token)


async def refresh_google_token(discord_user_id: str, token: dict[str, Any]) -> dict[str, Any]:
    """만료가 가까운 Google access token을 refresh token으로 갱신합니다."""
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Google refresh token이 없습니다.")
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("Google OAuth가 설정되어 있지 않습니다.")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        refreshed = response.json()

    refreshed["refresh_token"] = refresh_token
    _store_google_token(discord_user_id, refreshed)
    return get_google_token(discord_user_id)


def get_google_token(discord_user_id: str) -> dict[str, Any] | None:
    """Discord 사용자에게 저장된 Google OAuth token 정보를 조회합니다."""
    return get_token(discord_user_id)


def google_connected(discord_user_id: str) -> bool:
    """Discord 사용자가 Google Calendar를 연결했는지 확인합니다."""
    return get_google_token(discord_user_id) is not None


def get_calendar_recipients_for_source(
    *,
    source_id: int,
    source_owner_id: str,
) -> list[str]:
    """Return connected Google users who should receive this source's events.

    Managed sources such as ``system:rkmusic`` have no Google login of their
    own. Their recipients are users who used ``/route_add`` for the source and
    completed ``/google_connect``. Connected owners remain supported for
    user-owned sources.
    """
    return calendar_recipients(source_id, source_owner_id)


async def create_calendar_event(discord_user_id: str, event: dict[str, Any]) -> str:
    """일정 후보 정보를 Google Calendar event로 생성하고 Google event id를 반환합니다."""
    token = get_google_token(discord_user_id)
    if not token:
        raise RuntimeError("Google Calendar가 연결되어 있지 않습니다.")

    expires_at = token.get("expires_at")
    if expires_at and expires_at <= datetime.now(UTC) + timedelta(minutes=2):
        token = await refresh_google_token(discord_user_id, token)

    calendar_id = token.get("calendar_id") or settings.google_calendar_id
    payload = _to_google_event(event)

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_CALENDAR_EVENTS_URL.format(calendar_id=calendar_id),
            headers={"Authorization": f"Bearer {token['access_token']}"},
            json=payload,
        )
        response.raise_for_status()
        created = response.json()

    return created["id"]


async def create_calendar_events(
    discord_user_id: str,
    event: dict[str, Any],
    *,
    existing_event_types: set[str] | None = None,
) -> dict[str, str]:
    """공연 날짜와 예매/응모 날짜를 별도 Calendar 일정으로 생성합니다."""
    created = {}
    existing = existing_event_types or set()
    if event.get("starts_at") and "live" not in existing:
        created["live"] = await _create_calendar_event_from_payload(
            discord_user_id,
            _to_google_event(event),
        )
    if event.get("ticket_opens_at") and "ticket" not in existing:
        created["ticket"] = await _create_calendar_event_from_payload(
            discord_user_id,
            _to_ticket_google_event(event),
        )
    if not created and "notice" not in existing:
        created["notice"] = await _create_calendar_event_from_payload(
            discord_user_id,
            _to_google_event(event),
        )
    return created


async def _create_calendar_event_from_payload(discord_user_id: str, payload: dict[str, Any]) -> str:
    token = get_google_token(discord_user_id)
    if not token:
        raise RuntimeError("Google Calendar가 연결되어 있지 않습니다.")

    expires_at = token.get("expires_at")
    if expires_at and expires_at <= datetime.now(UTC) + timedelta(minutes=2):
        token = await refresh_google_token(discord_user_id, token)

    calendar_id = token.get("calendar_id") or settings.google_calendar_id
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_CALENDAR_EVENTS_URL.format(calendar_id=calendar_id),
            headers={"Authorization": f"Bearer {token['access_token']}"},
            json=payload,
        )
        response.raise_for_status()
        created = response.json()

    return created["id"]


def _store_google_token(discord_user_id: str, token: dict[str, Any]) -> None:
    """Google OAuth token 응답을 사용자별로 upsert 저장합니다."""
    save_token(discord_user_id, token)


def _to_google_event(event: dict[str, Any]) -> dict[str, Any]:
    """내부 일정 후보 dict를 Google Calendar events.insert payload로 변환합니다."""
    description = _build_description(event)

    starts_at = event.get("starts_at")
    if starts_at:
        if _is_date_only(starts_at):
            end_date = date.fromisoformat(starts_at) + timedelta(days=1)
            return {
                "summary": event["title"],
                "location": event.get("venue"),
                "description": description,
                "start": {"date": starts_at},
                "end": {"date": end_date.isoformat()},
            }

        end_at = _add_default_duration(starts_at)
        return {
            "summary": event["title"],
            "location": event.get("venue"),
            "description": description,
            "start": {"dateTime": starts_at},
            "end": {"dateTime": end_at},
        }

    return {
        "summary": event["title"],
        "location": event.get("venue"),
        "description": description,
        "start": {"date": datetime.now(UTC).date().isoformat()},
        "end": {"date": datetime.now(UTC).date().isoformat()},
    }


def _to_ticket_google_event(event: dict[str, Any]) -> dict[str, Any]:
    title = f"예매/응모 시작: {event['title']}"
    if event.get("ticket_closes_at"):
        title = f"예매/응모 기간: {event['title']}"

    starts_at = event["ticket_opens_at"]
    payload = {
        "summary": title,
        "location": event.get("venue"),
        "description": _build_description(event),
    }
    closes_at = event.get("ticket_closes_at")
    if _is_date_only(starts_at):
        end_date = date.fromisoformat(closes_at or starts_at) + timedelta(days=1)
        payload["start"] = {"date": starts_at}
        payload["end"] = {"date": end_date.isoformat()}
        return payload

    payload["start"] = {"dateTime": starts_at}
    payload["end"] = {"dateTime": closes_at or _add_default_duration(starts_at)}
    return payload


def _build_description(event: dict[str, Any]) -> str:
    description_parts = []
    if event.get("source_url"):
        description_parts.append(f"출처: {event['source_url']}")
    if event.get("ticket_url"):
        description_parts.append(f"예매: {event['ticket_url']}")
    if event.get("price_text"):
        description_parts.append(f"예매 정보:\n{event['price_text']}")
    if event.get("raw_text"):
        description_parts.append(event["raw_text"])
    return "\n\n".join(description_parts)


def _is_date_only(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return "T" not in value


def _add_default_duration(starts_at: str) -> str:
    """시작 시간만 있는 일정에 기본 2시간 종료 시간을 붙입니다."""
    parsed = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    return (parsed + timedelta(hours=2)).isoformat()
