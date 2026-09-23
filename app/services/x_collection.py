"""X polling orchestration with no classification or cross-collector side effects."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable
from uuid import uuid4

from app.db.catalog_session import catalog_runtime_session
from app.integrations.x_client import fetch_post_pages, post_url
from app.repositories.runtime_delivery import (
    StoredPost,
    XAccount,
    claim_x_accounts,
    fail_x_account,
    store_x_posts,
)

logger = logging.getLogger(__name__)
PageFetcher = Callable[[str, str | None], Awaitable[list[list[dict]]]]


@dataclass
class CollectionResult:
    accounts: int = 0
    posts_seen: int = 0
    posts_stored: int = 0
    deliveries_queued: int = 0
    failures: int = 0


def _published_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _newest_id(posts: list[dict], fallback: str | None) -> str | None:
    ids = [str(post["id"]) for post in posts if post.get("id")]
    if fallback:
        ids.append(fallback)
    if not ids:
        return fallback
    if all(value.isdigit() for value in ids):
        return max(ids, key=int)
    return max(ids)


async def collect_x_once(
    *,
    fetch_pages: PageFetcher = fetch_post_pages,
    worker_id: str | None = None,
    account_limit: int = 100,
    poll_interval_seconds: float = 0,
    fetch_timeout_seconds: float = 240,
) -> CollectionResult:
    """Collect every fetched page, then atomically persist and advance each cursor."""
    worker_id = worker_id or f"x-{uuid4()}"
    if not 0 < fetch_timeout_seconds < 300:
        raise ValueError("X fetch timeout must be shorter than its 300 second lease")
    result = CollectionResult()
    visited: list[int] = []
    for _ in range(account_limit):
        claim_owner = f"{worker_id}-{uuid4()}"
        with catalog_runtime_session() as session:
            accounts = claim_x_accounts(session, worker_id=claim_owner, limit=1,
                                        exclude_ids=tuple(visited))
        if not accounts:
            break
        account = accounts[0]
        visited.append(account.id)
        result.accounts += 1
        try:
            pages = await asyncio.wait_for(
                fetch_pages(account.platform_id, account.last_seen_external_id),
                timeout=fetch_timeout_seconds,
            )
            raw_posts = [post for page in pages for post in page]
            result.posts_seen += len(raw_posts)
            normalized = [
                StoredPost(
                    external_id=str(post["id"]),
                    source_url=post_url(account.handle, str(post["id"])),
                    raw_text=str(post.get("text") or ""),
                    published_at=_published_at(post.get("created_at")),
                )
                for post in sorted(
                    raw_posts,
                    key=lambda item: (
                        (0, int(item["id"]))
                        if str(item["id"]).isdigit()
                        else (1, str(item["id"]))
                    ),
                )
            ]
            with catalog_runtime_session() as session:
                stored, queued = store_x_posts(
                    session, account=account, posts=normalized,
                    next_cursor=_newest_id(raw_posts, account.last_seen_external_id),
                    poll_interval_seconds=poll_interval_seconds,
                )
            result.posts_stored += stored
            result.deliveries_queued += queued
        except Exception as exc:
            result.failures += 1
            logger.warning("X account %s collection failed (%s)", account.id, type(exc).__name__)
            try:
                with catalog_runtime_session() as session:
                    fail_x_account(
                        session, account_id=account.id, worker_id=account.lease_owner,
                        error=type(exc).__name__,
                    )
            except Exception:
                logger.error("Could not persist failure for X account %s", account.id)
    return result
