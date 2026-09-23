"""Auth HTTP endpoints, independent of application startup."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.integrations.google_calendar import (
    build_google_auth_url,
    exchange_code_for_tokens,
    google_oauth_configured,
)

router = APIRouter(tags=["auth"])


@router.get("/auth/google/start")
def start_google_auth(discord_user_id: str) -> RedirectResponse:
    """Discord 사용자 ID를 state로 담아 Google OAuth 로그인 화면으로 이동시킵니다."""
    if not google_oauth_configured():
        raise HTTPException(status_code=500, detail="Google OAuth가 설정되어 있지 않습니다.")
    return RedirectResponse(build_google_auth_url(discord_user_id))


@router.get("/auth/google/callback", response_class=HTMLResponse)
async def google_auth_callback(code: str, state: str) -> str:
    """Google OAuth callback에서 인증 code를 토큰으로 바꾸고 연결 완료 HTML을 보여줍니다."""
    await exchange_code_for_tokens(code, state)
    return """
    <html>
      <body>
        <h1>Google Calendar 연결 완료</h1>
        <p>이 페이지를 닫고 Discord로 돌아가도 됩니다.</p>
      </body>
    </html>
    """
