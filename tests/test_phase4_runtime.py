"""Phase-4 X collection and durable Discord delivery tests; local PostgreSQL only."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.bots.discord_bot import bot
from app.services import notification_delivery, x_collection
from app.services.notification_delivery import deliver_pending_once
from app.services.x_collection import collect_x_once
from test_catalog_migration import apply, database, local_server, row


@pytest.fixture
def runtime_store(database, monkeypatch):
    apply(database)
    info = database.info
    engine = create_engine(
        f"postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}"
    )

    @contextmanager
    def session_scope():
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(x_collection, "catalog_runtime_session", session_scope)
    monkeypatch.setattr(notification_delivery, "catalog_runtime_session", session_scope)
    yield database
    engine.dispose()


def seed_x_account(db, *, platform_id="42", handle="fixture", with_route=True):
    account = row(
        db, "external_accounts", platform="x", platform_id=platform_id,
        handle=handle, url=f"https://x.com/{handle}", collection_enabled=True,
    )
    if with_route:
        db.execute("INSERT INTO discord_users(discord_user_id) VALUES ('100') ON CONFLICT DO NOTHING")
        db.execute("""
            INSERT INTO discord_guilds(guild_id,owner_discord_user_id)
            VALUES ('200','100') ON CONFLICT DO NOTHING;
            INSERT INTO discord_channels(channel_id,guild_id)
            VALUES ('300','200') ON CONFLICT DO NOTHING
        """, prepare=False)
        row(
            db, "notification_routes", external_account_id=account,
            guild_id="200", channel_id="300", owner_discord_user_id="100",
        )
    db.commit()
    return account


def post(post_id: str, text_value: str = "raw post") -> dict:
    return {
        "id": post_id,
        "text": text_value,
        "created_at": "2026-09-22T00:00:00Z",
        "entities": {"urls": []},
    }


def test_collection_paginates_deduplicates_and_queues_routes(runtime_store):
    db = runtime_store
    account = seed_x_account(db)
    calls = []

    async def pages(platform_id, since_id):
        calls.append((platform_id, since_id))
        return [
            [post("103", "contains https://youtube.com/watch?v=abcdefghijk"), post("102")],
            [post("101")],
        ]

    first = asyncio.run(collect_x_once(fetch_pages=pages, worker_id="test-x"))
    second = asyncio.run(collect_x_once(fetch_pages=pages, worker_id="test-x-2"))

    assert first.posts_seen == 3 and first.posts_stored == 3
    assert first.deliveries_queued == 3 and first.failures == 0
    assert second.posts_stored == 0 and second.deliveries_queued == 0
    assert calls == [("42", None), ("42", "103")]
    assert db.execute(
        "SELECT external_id FROM source_items ORDER BY id"
    ).fetchall() == [("101",), ("102",), ("103",)]
    state = db.execute(
        "SELECT last_seen_external_id,status FROM collection_states WHERE external_account_id=%s",
        (account,),
    ).fetchone()
    assert state == ("103", "idle")
    assert db.execute("SELECT count(*) FROM notification_deliveries").fetchone()[0] == 3
    # A YouTube URL remains inert text; X collection creates no music job.
    assert db.execute("SELECT count(*) FROM worker_jobs").fetchone()[0] == 0


def test_collection_without_route_stores_post_without_delivery(runtime_store):
    db = runtime_store
    seed_x_account(db, platform_id="50", handle="noroute", with_route=False)

    async def pages(*_):
        return [[post("1")]]

    result = asyncio.run(collect_x_once(fetch_pages=pages))
    assert result.posts_stored == 1 and result.deliveries_queued == 0
    assert db.execute("SELECT count(*) FROM source_items").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM notification_deliveries").fetchone()[0] == 0


def test_collection_failure_preserves_cursor_and_schedules_retry(runtime_store):
    db = runtime_store
    account = seed_x_account(db)
    db.execute(
        "INSERT INTO collection_states(external_account_id,last_seen_external_id,cursor_value) "
        "VALUES (%s,'90','90')", (account,),
    )
    db.commit()

    async def fail(*_):
        raise RuntimeError("provider unavailable")

    result = asyncio.run(collect_x_once(fetch_pages=fail))
    state = db.execute("""
        SELECT last_seen_external_id,status,consecutive_failures,next_poll_at IS NOT NULL
        FROM collection_states WHERE external_account_id=%s
    """, (account,)).fetchone()
    assert result.failures == 1
    assert state == ("90", "backoff", 1, True)


class OfflineSender:
    def is_available(self):
        return False

    async def send_url(self, channel_id, url):
        raise AssertionError("offline sender must not be called")


class RecordingSender:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.messages = []

    def is_available(self):
        return True

    async def send_url(self, channel_id, url):
        self.messages.append((channel_id, url))
        if self.fail:
            raise RuntimeError("temporary Discord error")
        return "9001"


def seed_pending_delivery(db):
    account = seed_x_account(db)
    item = row(
        db, "source_items", external_account_id=account, external_id="post-1",
        source_url="https://x.com/fixture/status/post-1", raw_text="raw",
        published_at="2026-09-22T00:00:00Z",
    )
    route_id = db.execute("SELECT id FROM notification_routes").fetchone()[0]
    delivery = row(
        db, "notification_deliveries", route_id=route_id,
        source_item_id=item, status="pending",
    )
    db.commit()
    return delivery


def test_offline_sender_leaves_delivery_pending(runtime_store):
    db = runtime_store
    delivery = seed_pending_delivery(db)
    result = asyncio.run(deliver_pending_once(OfflineSender()))
    assert result.offline is True
    assert db.execute(
        "SELECT status,attempt_count FROM notification_deliveries WHERE id=%s", (delivery,)
    ).fetchone() == ("pending", 0)


def test_delivery_retries_then_sends_only_source_url(runtime_store):
    db = runtime_store
    delivery = seed_pending_delivery(db)
    failed_sender = RecordingSender(fail=True)
    failed = asyncio.run(deliver_pending_once(failed_sender, worker_id="delivery-1"))
    assert failed.retried == 1
    assert db.execute(
        "SELECT status,attempt_count FROM notification_deliveries WHERE id=%s", (delivery,)
    ).fetchone() == ("retry", 1)

    db.execute(
        "UPDATE notification_deliveries SET next_attempt_at=clock_timestamp() WHERE id=%s",
        (delivery,),
    )
    db.commit()
    sender = RecordingSender()
    sent = asyncio.run(deliver_pending_once(sender, worker_id="delivery-2"))
    assert sent.sent == 1
    assert sender.messages == [("300", "https://x.com/fixture/status/post-1")]
    assert db.execute("""
        SELECT status,attempt_count,discord_message_id,delivered_at IS NOT NULL
        FROM notification_deliveries WHERE id=%s
    """, (delivery,)).fetchone() == ("sent", 2, "9001", True)


def test_expired_sending_delivery_becomes_unknown_without_resend(runtime_store):
    db = runtime_store
    delivery = seed_pending_delivery(db)
    db.execute("""
        UPDATE notification_deliveries
        SET status='sending', attempt_count=1, lease_owner='dead',
            lease_expires_at=clock_timestamp() - interval '1 second'
        WHERE id=%s
    """, (delivery,))
    db.commit()
    sender = RecordingSender()
    result = asyncio.run(deliver_pending_once(sender))
    assert result.unknown == 1 and sender.messages == []
    assert db.execute(
        "SELECT status FROM notification_deliveries WHERE id=%s", (delivery,)
    ).fetchone()[0] == "unknown"


def test_discord_client_has_no_command_tree_or_management_surface():
    assert not hasattr(bot, "tree")
    for command in ("artist_add", "route_add", "source_test", "song_save", "google_connect"):
        assert not hasattr(bot, command)
