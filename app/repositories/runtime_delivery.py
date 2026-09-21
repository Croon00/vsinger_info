"""Unified-DB persistence for X collection and Discord delivery."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class XAccount:
    id: int
    platform_id: str
    handle: str
    last_seen_external_id: str | None
    lease_owner: str


@dataclass(frozen=True)
class StoredPost:
    external_id: str
    source_url: str
    raw_text: str
    published_at: datetime


@dataclass(frozen=True)
class PendingDelivery:
    id: int
    channel_id: str
    source_url: str
    attempt_count: int


def claim_x_accounts(
    session: Session,
    *,
    worker_id: str,
    limit: int = 100,
    lease_seconds: int = 300,
) -> list[XAccount]:
    """Lease enabled X accounts, creating missing collection state rows."""
    session.execute(text("""
        INSERT INTO collection_states (external_account_id)
        SELECT id FROM external_accounts
        WHERE platform='x' AND collection_enabled AND archived_at IS NULL
        ON CONFLICT (external_account_id) DO NOTHING
    """))
    rows = session.execute(text("""
        SELECT ea.id, ea.platform_id, ea.handle, cs.last_seen_external_id
        FROM external_accounts ea
        JOIN collection_states cs ON cs.external_account_id=ea.id
        WHERE ea.platform='x' AND ea.collection_enabled AND ea.archived_at IS NULL
          AND ea.platform_id IS NOT NULL AND ea.handle IS NOT NULL
          AND (cs.next_poll_at IS NULL OR cs.next_poll_at <= clock_timestamp())
          AND (cs.status IN ('idle','backoff','error')
               OR (cs.status='polling' AND cs.lease_expires_at < clock_timestamp()))
        ORDER BY ea.id
        FOR UPDATE OF cs SKIP LOCKED
        LIMIT :limit
    """), {"limit": limit}).mappings().all()
    if not rows:
        return []
    ids = [int(row["id"]) for row in rows]
    session.execute(
        text("""
            UPDATE collection_states
            SET status='polling', lease_owner=:worker_id,
                lease_expires_at=clock_timestamp() + (:lease_seconds * interval '1 second'),
                last_error=NULL
            WHERE external_account_id IN :ids
        """).bindparams(bindparam("ids", expanding=True)),
        {"worker_id": worker_id, "lease_seconds": lease_seconds, "ids": ids},
    )
    return [
        XAccount(
            id=int(row["id"]),
            platform_id=str(row["platform_id"]),
            handle=str(row["handle"]).lstrip("@"),
            last_seen_external_id=row["last_seen_external_id"],
            lease_owner=worker_id,
        )
        for row in rows
    ]


def store_x_posts(
    session: Session,
    *,
    account: XAccount,
    posts: Iterable[StoredPost],
    next_cursor: str | None,
) -> tuple[int, int]:
    """Atomically deduplicate posts, enqueue active routes, and advance cursor."""
    inserted = 0
    deliveries = 0
    for post in posts:
        item_id = session.execute(text("""
            INSERT INTO source_items (
              external_account_id, external_id, source_url, raw_text, published_at
            ) VALUES (:account_id,:external_id,:source_url,:raw_text,:published_at)
            ON CONFLICT (external_account_id, external_id) DO NOTHING
            RETURNING id
        """), {
            "account_id": account.id,
            "external_id": post.external_id,
            "source_url": post.source_url,
            "raw_text": post.raw_text,
            "published_at": post.published_at,
        }).scalar_one_or_none()
        if item_id is None:
            continue
        inserted += 1
        deliveries += int(session.execute(text("""
            WITH queued AS (
              INSERT INTO notification_deliveries (route_id, source_item_id)
              SELECT nr.id, :item_id
              FROM notification_routes nr
              JOIN discord_guilds dg ON dg.guild_id=nr.guild_id AND dg.is_active
              JOIN discord_channels dc ON dc.guild_id=nr.guild_id
                                       AND dc.channel_id=nr.channel_id AND dc.is_active
              WHERE nr.external_account_id=:account_id AND nr.is_active
              ON CONFLICT (route_id, source_item_id) DO NOTHING
              RETURNING 1
            ) SELECT count(*) FROM queued
        """), {"item_id": item_id, "account_id": account.id}).scalar_one())

    updated = session.execute(text("""
        UPDATE collection_states
        SET cursor_value=:cursor, last_seen_external_id=:cursor,
            status='idle', consecutive_failures=0, next_poll_at=NULL,
            lease_owner=NULL, lease_expires_at=NULL,
            last_polled_at=clock_timestamp(), last_error=NULL
        WHERE external_account_id=:account_id AND status='polling'
          AND lease_owner=:lease_owner
    """), {"cursor": next_cursor or account.last_seen_external_id,
             "account_id": account.id, "lease_owner": account.lease_owner})
    if updated.rowcount != 1:
        raise RuntimeError(f"X collection lease was lost for account {account.id}")
    return inserted, deliveries


def fail_x_account(
    session: Session,
    *,
    account_id: int,
    worker_id: str,
    error: str,
    max_backoff_seconds: int = 3600,
) -> None:
    """Release a failed poll lease and schedule exponential retry."""
    session.execute(text("""
        UPDATE collection_states
        SET status='backoff', consecutive_failures=consecutive_failures+1,
            next_poll_at=clock_timestamp() +
              (LEAST(:max_backoff, 30 * power(2, LEAST(consecutive_failures, 7))) * interval '1 second'),
            lease_owner=NULL, lease_expires_at=NULL, last_error=:error,
            last_polled_at=clock_timestamp()
        WHERE external_account_id=:account_id AND status='polling' AND lease_owner=:worker_id
    """), {"account_id": account_id, "worker_id": worker_id,
             "error": error[:2000], "max_backoff": max_backoff_seconds})


def claim_deliveries(
    session: Session,
    *,
    worker_id: str,
    limit: int = 100,
    lease_seconds: int = 120,
) -> tuple[list[PendingDelivery], int, int]:
    """Mark invalid routes skipped and lease due deliveries.

    Expired ``sending`` rows become ``unknown`` because Discord may have accepted
    the message before the process lost its DB connection. They are never retried
    automatically, preventing duplicate public messages.
    """
    unknown = int(session.execute(text("""
        WITH changed AS (
          UPDATE notification_deliveries
          SET status='unknown', lease_owner=NULL, lease_expires_at=NULL,
              last_error='delivery lease expired after send may have started'
          WHERE status='sending' AND lease_expires_at < clock_timestamp()
          RETURNING 1
        ) SELECT count(*) FROM changed
    """)).scalar_one())
    skipped = int(session.execute(text("""
        WITH changed AS (
          UPDATE notification_deliveries nd
          SET status='skipped', next_attempt_at=NULL,
              last_error='route, channel, guild, or source is inactive'
          FROM notification_routes nr
          JOIN external_accounts ea ON ea.id=nr.external_account_id
          JOIN discord_guilds dg ON dg.guild_id=nr.guild_id
          JOIN discord_channels dc ON dc.guild_id=nr.guild_id AND dc.channel_id=nr.channel_id
          WHERE nd.route_id=nr.id AND nd.status IN ('pending','retry')
            AND (NOT nr.is_active OR NOT ea.collection_enabled OR ea.archived_at IS NOT NULL
                 OR NOT dg.is_active OR NOT dc.is_active)
          RETURNING 1
        ) SELECT count(*) FROM changed
    """)).scalar_one())
    rows = session.execute(text("""
        SELECT nd.id, nr.channel_id, si.source_url, nd.attempt_count
        FROM notification_deliveries nd
        JOIN notification_routes nr ON nr.id=nd.route_id AND nr.is_active
        JOIN external_accounts ea ON ea.id=nr.external_account_id
                                  AND ea.collection_enabled AND ea.archived_at IS NULL
        JOIN discord_guilds dg ON dg.guild_id=nr.guild_id AND dg.is_active
        JOIN discord_channels dc ON dc.guild_id=nr.guild_id
                                 AND dc.channel_id=nr.channel_id AND dc.is_active
        JOIN source_items si ON si.id=nd.source_item_id
        WHERE nd.status IN ('pending','retry')
          AND (nd.next_attempt_at IS NULL OR nd.next_attempt_at <= clock_timestamp())
        ORDER BY nd.id
        FOR UPDATE OF nd SKIP LOCKED
        LIMIT :limit
    """), {"limit": limit}).mappings().all()
    if rows:
        session.execute(
            text("""
                UPDATE notification_deliveries
                SET status='sending', attempt_count=attempt_count+1,
                    lease_owner=:worker_id,
                    lease_expires_at=clock_timestamp() + (:lease_seconds * interval '1 second'),
                    last_error=NULL
                WHERE id IN :ids
            """).bindparams(bindparam("ids", expanding=True)),
            {"worker_id": worker_id, "lease_seconds": lease_seconds,
             "ids": [int(row["id"]) for row in rows]},
        )
    return ([
        PendingDelivery(
            id=int(row["id"]), channel_id=str(row["channel_id"]),
            source_url=str(row["source_url"]), attempt_count=int(row["attempt_count"]) + 1,
        ) for row in rows
    ], skipped, unknown)


def mark_delivery_sent(session: Session, delivery_id: int, message_id: str) -> None:
    session.execute(text("""
        UPDATE notification_deliveries
        SET status='sent', discord_message_id=:message_id,
            delivered_at=clock_timestamp(), next_attempt_at=NULL,
            lease_owner=NULL, lease_expires_at=NULL, last_error=NULL
        WHERE id=:id AND status='sending'
    """), {"id": delivery_id, "message_id": message_id})


def mark_delivery_retry(
    session: Session,
    delivery_id: int,
    *,
    error: str,
    attempt_count: int,
    max_attempts: int = 5,
) -> None:
    terminal = attempt_count >= max_attempts
    delay = min(3600, 30 * (2 ** max(0, attempt_count - 1)))
    session.execute(text("""
        UPDATE notification_deliveries
        SET status=:status,
            next_attempt_at=CASE WHEN :terminal THEN NULL ELSE clock_timestamp() + (:delay * interval '1 second') END,
            lease_owner=NULL, lease_expires_at=NULL, last_error=:error
        WHERE id=:id AND status='sending'
    """), {"id": delivery_id, "status": "failed" if terminal else "retry",
             "terminal": terminal, "delay": delay, "error": error[:2000]})
