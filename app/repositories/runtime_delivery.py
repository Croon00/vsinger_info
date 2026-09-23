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
    baseline_initialized: bool


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
    guild_id: str
    route_version: int
    lease_owner: str


def claim_x_accounts(
    session: Session,
    *,
    worker_id: str,
    limit: int = 100,
    lease_seconds: int = 300,
    exclude_ids: tuple[int, ...] = (),
) -> list[XAccount]:
    """Lease enabled X accounts, creating missing collection state rows."""
    session.execute(text("""
        INSERT INTO collection_states (external_account_id)
        SELECT id FROM external_accounts
        WHERE platform='x' AND collection_enabled AND archived_at IS NULL
        ON CONFLICT (external_account_id) DO NOTHING
    """))
    session.execute(text("""
        UPDATE collection_states cs SET status='error',
            last_error='X account requires a numeric platform_id and a nonempty handle'
        FROM external_accounts ea
        WHERE ea.id=cs.external_account_id AND ea.platform='x'
          AND ea.collection_enabled AND ea.archived_at IS NULL
          AND cs.status <> 'polling'
          AND (ea.platform_id IS NULL OR ea.platform_id !~ '^[0-9]+$'
               OR NULLIF(ltrim(btrim(ea.handle),'@'),'') IS NULL)
          AND cs.last_error IS DISTINCT FROM
              'X account requires a numeric platform_id and a nonempty handle'
    """))
    rows = session.execute(text("""
        SELECT ea.id, ea.platform_id, ea.handle, cs.last_seen_external_id,
               cs.provider_state->>'x_baseline_initialized' AS baseline_initialized
        FROM external_accounts ea
        JOIN collection_states cs ON cs.external_account_id=ea.id
        WHERE ea.platform='x' AND ea.collection_enabled AND ea.archived_at IS NULL
          AND ea.platform_id ~ '^[0-9]+$'
          AND NULLIF(ltrim(btrim(ea.handle),'@'),'') IS NOT NULL
          AND ea.id NOT IN :exclude_ids
          AND (cs.status='disabled' OR cs.next_poll_at IS NULL OR cs.next_poll_at <= clock_timestamp())
          AND (cs.status IN ('idle','backoff','error','disabled')
               OR (cs.status='polling' AND cs.lease_expires_at < clock_timestamp()))
        ORDER BY cs.last_polled_at NULLS FIRST, ea.id
        FOR UPDATE OF cs SKIP LOCKED
        LIMIT :limit
    """).bindparams(bindparam("exclude_ids", expanding=True)),
        {"limit": limit, "exclude_ids": exclude_ids}).mappings().all()
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
            baseline_initialized=(row["last_seen_external_id"] is not None
                                  or row["baseline_initialized"] == "true"),
        )
        for row in rows
    ]


def store_x_posts(
    session: Session,
    *,
    account: XAccount,
    posts: Iterable[StoredPost],
    next_cursor: str | None,
    poll_interval_seconds: float = 0,
) -> tuple[int, int]:
    """Atomically deduplicate posts, enqueue active routes, and advance cursor."""
    valid = session.execute(text("""
        SELECT cs.external_account_id FROM collection_states cs
        JOIN external_accounts ea ON ea.id=cs.external_account_id
        WHERE cs.external_account_id=:id AND cs.status='polling'
          AND cs.lease_owner=:owner AND cs.lease_expires_at > clock_timestamp()
          AND ea.collection_enabled AND ea.archived_at IS NULL AND ea.platform='x'
          AND ea.platform_id=:platform_id AND ltrim(ea.handle,'@')=:handle
        FOR UPDATE OF cs, ea
    """), {"id": account.id, "owner": account.lease_owner,
             "platform_id": account.platform_id, "handle": account.handle}).scalar_one_or_none()
    if valid is None:
        raise RuntimeError("X account changed or collection lease expired")
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
        if not account.baseline_initialized:
            continue
        if (account.last_seen_external_id and account.last_seen_external_id.isdigit()
                and post.external_id.isdigit()
                and int(post.external_id) <= int(account.last_seen_external_id)):
            continue
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
            status='idle', consecutive_failures=0,
            next_poll_at=clock_timestamp() + (:poll_interval * interval '1 second'),
            provider_state=provider_state || jsonb_build_object('x_baseline_initialized',true),
            lease_owner=NULL, lease_expires_at=NULL,
            last_polled_at=clock_timestamp(), last_error=NULL
        WHERE external_account_id=:account_id AND status='polling'
          AND lease_owner=:lease_owner AND lease_expires_at > clock_timestamp()
    """), {"cursor": next_cursor or account.last_seen_external_id,
             "account_id": account.id, "lease_owner": account.lease_owner,
             "poll_interval": max(0, poll_interval_seconds)})
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
          AND lease_expires_at > clock_timestamp()
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
        SELECT nd.id, nr.channel_id, nr.guild_id, nr.version AS route_version,
               si.source_url, nd.attempt_count
        FROM notification_deliveries nd
        JOIN notification_routes nr ON nr.id=nd.route_id AND nr.is_active
        JOIN external_accounts ea ON ea.id=nr.external_account_id
                                  AND ea.collection_enabled AND ea.archived_at IS NULL
        JOIN discord_guilds dg ON dg.guild_id=nr.guild_id AND dg.is_active
        JOIN discord_channels dc ON dc.guild_id=nr.guild_id
                                 AND dc.channel_id=nr.channel_id AND dc.is_active
        JOIN source_items si ON si.id=nd.source_item_id
                            AND si.external_account_id=nr.external_account_id
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
            guild_id=str(row["guild_id"]), route_version=int(row["route_version"]),
            lease_owner=worker_id,
        ) for row in rows
    ], skipped, unknown)


def delivery_is_current(session: Session, delivery: PendingDelivery) -> bool:
    """Recheck route identity, ownership state and the unexpired claim before I/O."""
    return session.execute(text("""
        SELECT nd.id FROM notification_deliveries nd
        JOIN notification_routes nr ON nr.id=nd.route_id
        JOIN external_accounts ea ON ea.id=nr.external_account_id
        JOIN source_items si ON si.id=nd.source_item_id AND si.external_account_id=ea.id
        JOIN discord_guilds dg ON dg.guild_id=nr.guild_id
        JOIN discord_channels dc ON dc.channel_id=nr.channel_id AND dc.guild_id=nr.guild_id
        LEFT JOIN discord_users du ON du.discord_user_id=nr.owner_discord_user_id
        WHERE nd.id=:id AND nd.status='sending' AND nd.lease_owner=:owner
          AND nd.lease_expires_at > clock_timestamp()
          AND nr.version=:version AND nr.channel_id=:channel AND nr.guild_id=:guild
          AND nr.is_active AND ea.collection_enabled AND ea.archived_at IS NULL
          AND dg.is_active AND dc.is_active AND (du.is_active OR du.discord_user_id IS NULL)
          AND si.source_url=:url
    """), {"id": delivery.id, "owner": delivery.lease_owner,
             "version": delivery.route_version, "channel": delivery.channel_id,
             "guild": delivery.guild_id, "url": delivery.source_url}).scalar_one_or_none() is not None


def mark_delivery_sent(session: Session, delivery_id: int, message_id: str, *, worker_id: str) -> bool:
    result = session.execute(text("""
        UPDATE notification_deliveries
        SET status='sent', discord_message_id=:message_id,
            delivered_at=clock_timestamp(), next_attempt_at=NULL,
            lease_owner=NULL, lease_expires_at=NULL, last_error=NULL
        WHERE id=:id AND status='sending' AND lease_owner=:worker_id
          AND lease_expires_at > clock_timestamp()
    """), {"id": delivery_id, "message_id": message_id, "worker_id": worker_id})
    return result.rowcount == 1


def finish_delivery(session: Session, delivery: PendingDelivery, *, status: str, error: str) -> bool:
    if status not in {"unknown", "skipped", "failed"}:
        raise ValueError("Unsupported terminal delivery status")
    result = session.execute(text("""
        UPDATE notification_deliveries SET status=:status, next_attempt_at=NULL,
            lease_owner=NULL, lease_expires_at=NULL, last_error=:error
        WHERE id=:id AND status='sending' AND lease_owner=:owner
          AND lease_expires_at > clock_timestamp()
    """), {"id": delivery.id, "owner": delivery.lease_owner,
             "status": status, "error": error[:2000]})
    return result.rowcount == 1


def mark_delivery_retry(
    session: Session,
    delivery_id: int,
    *,
    error: str,
    attempt_count: int,
    max_attempts: int = 5,
    worker_id: str,
    retry_after: float = 0,
) -> bool:
    terminal = attempt_count >= max_attempts
    delay = max(retry_after, min(3600, 30 * (2 ** max(0, attempt_count - 1))))
    result = session.execute(text("""
        UPDATE notification_deliveries
        SET status=:status,
            next_attempt_at=CASE WHEN :terminal THEN NULL ELSE clock_timestamp() + (:delay * interval '1 second') END,
            lease_owner=NULL, lease_expires_at=NULL, last_error=:error
        WHERE id=:id AND status='sending' AND lease_owner=:worker_id
          AND lease_expires_at > clock_timestamp()
    """), {"id": delivery_id, "status": "failed" if terminal else "retry",
             "terminal": terminal, "delay": delay, "error": error[:2000], "worker_id": worker_id})
    return result.rowcount == 1
