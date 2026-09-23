from __future__ import annotations

import asyncio
from contextlib import aclosing
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


X_API_BASE_URL = "https://api.x.com/2"
_twscrape_api: Any | None = None
_twscrape_lock = asyncio.Lock()


def x_configured() -> bool:
    """선택된 X 수집 방식에 필요한 인증정보가 설정되어 있는지 확인합니다."""
    provider = x_provider()
    if provider == "twscrape":
        return bool(settings.twscrape_auth_token and settings.twscrape_ct0)
    return bool(settings.x_bearer_token)


def x_provider() -> str:
    """명시적 설정을 우선하고 auto에서는 twscrape, X API 순으로 선택합니다."""
    if settings.x_provider != "auto":
        return settings.x_provider
    if settings.twscrape_auth_token and settings.twscrape_ct0:
        return "twscrape"
    return "x_api"


async def get_x_user_id(username: str) -> str:
    """X username을 X API 내부 user id로 변환합니다."""
    if x_provider() == "twscrape":
        api = await _get_twscrape_api()
        user = await api.user_by_login(username)
        if user is None:
            raise RuntimeError(f"X 사용자를 찾을 수 없습니다: {username}")
        return str(user.id)

    if not settings.x_bearer_token:
        raise RuntimeError("X_BEARER_TOKEN이 설정되어 있지 않습니다.")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{X_API_BASE_URL}/users/by/username/{username}",
            headers=_headers(),
        )
        response.raise_for_status()
        data = response.json()
    return data["data"]["id"]


async def get_x_profile_image_url(username: str) -> str:
    """Get a user's original-size X profile image without using a third-party avatar cache."""
    clean_username = username.strip().lstrip("@")
    if x_provider() == "twscrape":
        api = await _get_twscrape_api()
        user = await api.user_by_login(clean_username)
        if user is None or not user.profileImageUrl:
            raise RuntimeError(f"X user profile image was not found: {clean_username}")
        return str(user.profileImageUrl).replace("_normal.", ".")

    if not settings.x_bearer_token:
        raise RuntimeError("X_BEARER_TOKEN is not configured.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{X_API_BASE_URL}/users/by/username/{clean_username}",
            headers=_headers(),
            params={"user.fields": "profile_image_url"},
        )
        response.raise_for_status()
        image_url = response.json().get("data", {}).get("profile_image_url")
    if not image_url:
        raise RuntimeError(f"X user profile image was not found: {clean_username}")
    return str(image_url).replace("_normal.", ".")


async def fetch_recent_posts(
    user_id: str,
    since_id: str | None = None,
    *,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """특정 X user id의 최신 원본 게시물을 가져오고, since_id 이후만 조회할 수 있습니다."""
    if not 5 <= max_results <= 100:
        raise ValueError("max_results must be between 5 and 100.")

    if x_provider() == "twscrape":
        return await _fetch_recent_posts_twscrape(user_id, since_id, max_results)

    if not settings.x_bearer_token:
        raise RuntimeError("X_BEARER_TOKEN이 설정되어 있지 않습니다.")

    data = await _fetch_x_api_page(user_id, since_id, max_results=max_results)
    return data.get("data", [])


async def fetch_post_pages(
    user_id: str,
    since_id: str | None = None,
    *,
    page_size: int = 100,
    max_pages: int = 20,
) -> list[list[dict[str, Any]]]:
    """Fetch all bounded pages after ``since_id`` without advancing DB state."""
    if not 5 <= page_size <= 100:
        raise ValueError("page_size must be between 5 and 100")
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages must be between 1 and 100")
    if x_provider() == "twscrape":
        capacity = page_size * max_pages
        posts = await _fetch_recent_posts_twscrape(
            user_id, since_id, capacity + 1
        )
        if len(posts) > capacity:
            raise RuntimeError(
                f"X pagination exceeded the safety limit ({max_pages} pages); cursor was not advanced"
            )
        return [posts[index:index + page_size] for index in range(0, len(posts), page_size)]

    pages: list[list[dict[str, Any]]] = []
    token: str | None = None
    for _ in range(max_pages):
        payload = await _fetch_x_api_page(
            user_id, since_id, max_results=page_size, pagination_token=token
        )
        page = payload.get("data", [])
        if page:
            pages.append(page)
        token = payload.get("meta", {}).get("next_token")
        if not token:
            return pages
    if token:
        raise RuntimeError(
            f"X pagination exceeded the safety limit ({max_pages} pages); cursor was not advanced"
        )
    return pages


async def _fetch_x_api_page(
    user_id: str,
    since_id: str | None,
    *,
    max_results: int,
    pagination_token: str | None = None,
) -> dict[str, Any]:
    if not settings.x_bearer_token:
        raise RuntimeError("X_BEARER_TOKEN이 설정되어 있지 않습니다.")
    params = {
        "max_results": str(max_results),
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies",
    }
    if since_id:
        params["since_id"] = since_id
    if pagination_token:
        params["pagination_token"] = pagination_token

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{X_API_BASE_URL}/users/{user_id}/tweets",
            headers=_headers(),
            params=params,
        )
        response.raise_for_status()
        return response.json()


def post_url(username: str, post_id: str) -> str:
    """X username과 게시물 ID로 브라우저에서 열 수 있는 게시물 URL을 만듭니다."""
    return f"https://x.com/{username}/status/{post_id}"


def _headers() -> dict[str, str]:
    """X API 요청에 공통으로 사용하는 Authorization header를 만듭니다."""
    return {"Authorization": f"Bearer {settings.x_bearer_token}"}


async def _get_twscrape_api() -> Any:
    """쿠키 계정 DB를 준비하고 재사용 가능한 twscrape API를 반환합니다."""
    global _twscrape_api
    if _twscrape_api is not None:
        return _twscrape_api

    async with _twscrape_lock:
        if _twscrape_api is not None:
            return _twscrape_api
        if not settings.twscrape_auth_token or not settings.twscrape_ct0:
            raise RuntimeError(
                "TWSCRAPE_AUTH_TOKEN과 TWSCRAPE_CT0가 설정되어 있지 않습니다."
            )

        from twscrape import API

        db_path = Path(settings.twscrape_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        api = API(
            str(db_path),
            raise_when_no_account=True,
            wait_timeout=30,
        )
        cookies = {
            "auth_token": settings.twscrape_auth_token,
            "ct0": settings.twscrape_ct0,
        }
        existing = await api.pool.get_account(settings.twscrape_username)
        if existing is not None and any(
            existing.cookies.get(name) != value for name, value in cookies.items()
        ):
            await api.pool.delete_accounts(settings.twscrape_username)
            existing = None
        if existing is None:
            cookie_text = (
                f"auth_token={settings.twscrape_auth_token}; "
                f"ct0={settings.twscrape_ct0}"
            )
            await api.pool.add_account_cookies(
                settings.twscrape_username,
                cookie_text,
            )

        _twscrape_api = api
        return api


async def _fetch_recent_posts_twscrape(
    user_id: str,
    since_id: str | None,
    max_results: int,
) -> list[dict[str, Any]]:
    """twscrape 사용자 타임라인을 기존 X API 응답 형태로 변환합니다."""
    api = await _get_twscrape_api()
    posts: list[dict[str, Any]] = []
    since_value = int(since_id) if since_id else None

    async with aclosing(api.user_tweets(int(user_id), limit=max_results)) as tweets:
        async for tweet in tweets:
            if since_value is not None and tweet.id <= since_value:
                continue
            if tweet.retweetedTweet is not None or tweet.inReplyToTweetId is not None:
                continue
            posts.append(_tweet_to_post(tweet))
            if len(posts) >= max_results:
                break

    return posts


def _tweet_to_post(tweet: Any) -> dict[str, Any]:
    """twscrape Tweet을 scheduler가 사용하는 X API v2 형태로 맞춥니다."""
    urls = [
        {
            "url": link.tcourl or link.url,
            "expanded_url": link.url,
        }
        for link in (tweet.links or [])
    ]
    return {
        "id": str(tweet.id),
        "text": tweet.rawContent,
        "created_at": tweet.date.isoformat(),
        "entities": {"urls": urls},
    }
