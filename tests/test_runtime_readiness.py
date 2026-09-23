"""Service readiness regressions: all external I/O is fake.

All database fixtures are disposable local PostgreSQL; all providers are fake.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from test_catalog_migration import database, local_server
from test_phase4_runtime import (
    runtime_store, seed_x_account, seed_pending_delivery, post, RecordingSender,
)
from app.services import notification_delivery
from app.services.x_collection import collect_x_once
from app.services.notification_delivery import deliver_pending_once
from app.bots.discord_bot import ScheduleMusicBot


def test_new_account_first_poll_does_not_notify_history(runtime_store):
    seed_x_account(runtime_store)

    async def pages(*_):
        return [[post("10"), post("11")]]

    result = asyncio.run(collect_x_once(fetch_pages=pages))
    assert result.deliveries_queued == 0


def test_later_accounts_are_eventually_polled(runtime_store):
    for number in range(3):
        seed_x_account(runtime_store, platform_id=str(number + 1),
                       handle=f"fixture{number}", with_route=False)
    calls = []

    async def pages(platform_id, *_):
        calls.append(platform_id)
        return []

    for _ in range(2):
        asyncio.run(collect_x_once(fetch_pages=pages, account_limit=2))
    assert set(calls) == {"1", "2", "3"}


def test_collection_enabled_is_the_only_enable_switch(runtime_store):
    account = seed_x_account(runtime_store, with_route=False)
    runtime_store.execute(
        "INSERT INTO collection_states(external_account_id,status) VALUES (%s,'disabled')",
        (account,),
    )
    runtime_store.commit()

    async def pages(*_):
        return []

    result = asyncio.run(collect_x_once(fetch_pages=pages))
    assert result.accounts == 1


def test_sent_message_is_not_resent_after_db_receipt_failure(runtime_store, monkeypatch):
    delivery = seed_pending_delivery(runtime_store)
    sender = RecordingSender()
    original = notification_delivery.mark_delivery_sent

    def unavailable(*_, **kwargs):
        raise RuntimeError("simulated receipt write failure after accepted send")

    monkeypatch.setattr(notification_delivery, "mark_delivery_sent", unavailable)
    asyncio.run(deliver_pending_once(sender))
    monkeypatch.setattr(notification_delivery, "mark_delivery_sent", original)
    runtime_store.execute(
        "UPDATE notification_deliveries SET next_attempt_at=clock_timestamp() WHERE id=%s",
        (delivery,),
    )
    runtime_store.commit()
    asyncio.run(deliver_pending_once(sender))
    assert len(sender.messages) == 1


def test_ready_bot_can_resolve_uncached_channel(monkeypatch):
    client = ScheduleMusicBot()
    from types import SimpleNamespace
    channel = SimpleNamespace(
        guild=SimpleNamespace(id=200, me=object()),
        permissions_for=lambda _: SimpleNamespace(view_channel=True, send_messages=True),
        send=AsyncMock(return_value=SimpleNamespace(id=9001)),
    )
    monkeypatch.setattr(client, "is_available", lambda: True)
    monkeypatch.setattr(client, "get_channel", lambda _: None)
    monkeypatch.setattr(client, "fetch_channel", AsyncMock(return_value=channel))
    assert asyncio.run(client.send_url("300", "https://x.com/fixture/status/1", guild_id="200")) == "9001"


def test_route_is_rechecked_before_external_send(runtime_store, monkeypatch):
    delivery = seed_pending_delivery(runtime_store)
    sender = RecordingSender()
    original = notification_delivery.claim_deliveries

    def deactivate_after_claim(session, **kwargs):
        from sqlalchemy import text
        result = original(session, **kwargs)
        session.execute(text("UPDATE notification_routes SET is_active=false"))
        return result

    monkeypatch.setattr(notification_delivery, "claim_deliveries", deactivate_after_claim)
    asyncio.run(deliver_pending_once(sender))
    assert sender.messages == []


def test_empty_first_poll_initializes_baseline_and_new_post_notifies(runtime_store):
    seed_x_account(runtime_store)
    calls = 0

    async def pages(*_):
        nonlocal calls
        calls += 1
        return [] if calls == 1 else [[post("20")]]

    assert asyncio.run(collect_x_once(fetch_pages=pages)).deliveries_queued == 0
    assert asyncio.run(collect_x_once(fetch_pages=pages)).deliveries_queued == 1


def test_failed_first_poll_does_not_initialize_baseline(runtime_store):
    seed_x_account(runtime_store)

    async def fail(*_):
        raise TimeoutError()

    asyncio.run(collect_x_once(fetch_pages=fail))
    assert runtime_store.execute(
        "SELECT provider_state->>'x_baseline_initialized' FROM collection_states"
    ).fetchone()[0] is None
    runtime_store.execute("UPDATE collection_states SET next_poll_at=NULL")
    runtime_store.commit()

    async def pages(*_):
        return [[post("20")]]

    assert asyncio.run(collect_x_once(fetch_pages=pages)).deliveries_queued == 0


@pytest.mark.parametrize("change", [
    "UPDATE external_accounts SET collection_enabled=false",
    "UPDATE external_accounts SET platform_id='900'",
    "UPDATE collection_states SET lease_expires_at=clock_timestamp()-interval '1 second'",
])
def test_account_change_or_expired_lease_blocks_all_writes(runtime_store, change):
    seed_x_account(runtime_store)

    async def pages(*_):
        runtime_store.execute(change)
        runtime_store.commit()
        return [[post("30")]]

    result = asyncio.run(collect_x_once(fetch_pages=pages))
    assert result.failures == 1
    assert runtime_store.execute("SELECT count(*) FROM source_items").fetchone()[0] == 0
    assert runtime_store.execute("SELECT last_seen_external_id FROM collection_states").fetchone()[0] is None


def test_only_due_accounts_are_fetched_and_cursor_never_regresses(runtime_store):
    account = seed_x_account(runtime_store)
    runtime_store.execute(
        "INSERT INTO collection_states(external_account_id,last_seen_external_id) VALUES (%s,'40')",
        (account,),
    )
    runtime_store.commit()

    async def pages(*_):
        return [[post("39")]]

    first = asyncio.run(collect_x_once(fetch_pages=pages, poll_interval_seconds=60))
    second = asyncio.run(collect_x_once(fetch_pages=pages, poll_interval_seconds=60))
    assert first.accounts == 1 and second.accounts == 0
    assert first.deliveries_queued == 0
    assert runtime_store.execute("SELECT last_seen_external_id FROM collection_states").fetchone()[0] == "40"


def test_parallel_collectors_do_not_poll_same_account(runtime_store):
    seed_x_account(runtime_store)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def pages(*_):
            entered.set()
            await release.wait()
            return [[post("50")]]

        first = asyncio.create_task(collect_x_once(fetch_pages=pages))
        await entered.wait()
        second = await collect_x_once(fetch_pages=pages)
        release.set()
        await first
        assert second.accounts == 0

    asyncio.run(scenario())


def test_provider_timeout_releases_account_without_cursor(runtime_store):
    seed_x_account(runtime_store)

    async def blocked(*_):
        await asyncio.Event().wait()

    result = asyncio.run(collect_x_once(fetch_pages=blocked, fetch_timeout_seconds=0.01))
    assert result.failures == 1
    assert runtime_store.execute(
        "SELECT status, last_seen_external_id, lease_owner FROM collection_states"
    ).fetchone() == ("backoff", None, None)


def test_missing_identity_is_reported_without_provider_call(runtime_store):
    seed_x_account(runtime_store, platform_id="invalid")
    fetch = AsyncMock()
    assert asyncio.run(collect_x_once(fetch_pages=fetch)).accounts == 0
    fetch.assert_not_awaited()
    status, error = runtime_store.execute("SELECT status,last_error FROM collection_states").fetchone()
    assert status == "error" and "platform_id" in error


def test_transient_receipt_failure_retries_only_database(runtime_store, monkeypatch):
    seed_pending_delivery(runtime_store)
    sender = RecordingSender()
    original = notification_delivery.mark_delivery_sent
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("receipt failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(notification_delivery, "mark_delivery_sent", fail_once)
    assert asyncio.run(deliver_pending_once(sender)).sent == 1
    assert calls == 2 and len(sender.messages) == 1
    assert runtime_store.execute("SELECT status,discord_message_id FROM notification_deliveries").fetchone() == ("sent", "9001")


@pytest.mark.parametrize("kind", ["timeout", "cancelled", "exception", "invalid_receipt"])
def test_uncertain_send_is_never_retried(runtime_store, kind):
    seed_pending_delivery(runtime_store)
    sender = RecordingSender()

    async def uncertain(*_, **kwargs):
        if kind == "timeout":
            await asyncio.Event().wait()
        if kind == "cancelled":
            raise asyncio.CancelledError()
        if kind == "exception":
            raise RuntimeError("connection lost after POST")
        return "bad-receipt"

    sender.send_url = uncertain
    if kind == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(deliver_pending_once(sender))
    else:
        assert asyncio.run(deliver_pending_once(sender, send_timeout_seconds=0.01)).unknown == 1
    assert runtime_store.execute("SELECT status FROM notification_deliveries").fetchone()[0] == "unknown"
    next_sender = RecordingSender()
    asyncio.run(deliver_pending_once(next_sender))
    assert next_sender.messages == []


def test_retry_after_and_permanent_rejections(runtime_store):
    from app.services.delivery_errors import DeliveryPermanentError, DeliveryRetryableError
    seed_pending_delivery(runtime_store)
    sender = RecordingSender()
    sender.send_url = AsyncMock(side_effect=DeliveryRetryableError("429", retry_after=4000))
    assert asyncio.run(deliver_pending_once(sender)).retried == 1
    assert runtime_store.execute(
        "SELECT next_attempt_at > clock_timestamp()+interval '3900 seconds' FROM notification_deliveries"
    ).fetchone()[0]
    runtime_store.execute("UPDATE notification_deliveries SET next_attempt_at=NULL")
    runtime_store.commit()
    sender.send_url = AsyncMock(side_effect=DeliveryPermanentError("403"))
    assert asyncio.run(deliver_pending_once(sender)).failed == 1
    assert runtime_store.execute("SELECT status FROM notification_deliveries").fetchone()[0] == "failed"


def test_stale_delivery_owner_cannot_change_result(runtime_store):
    from app.repositories.runtime_delivery import mark_delivery_sent, mark_delivery_retry
    delivery = seed_pending_delivery(runtime_store)
    with notification_delivery.catalog_runtime_session() as session:
        notification_delivery.claim_deliveries(session, worker_id="new-owner", limit=1)
    with notification_delivery.catalog_runtime_session() as session:
        assert not mark_delivery_sent(session, delivery, "9001", worker_id="old-owner")
        assert not mark_delivery_retry(session, delivery, error="stale", attempt_count=1,
                                       worker_id="old-owner")
    assert runtime_store.execute("SELECT status,lease_owner FROM notification_deliveries").fetchone() == ("sending", "new-owner")


def test_parallel_senders_do_not_send_same_delivery(runtime_store):
    seed_pending_delivery(runtime_store)
    first_sender, second_sender = RecordingSender(), RecordingSender()

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def send(*args, **kwargs):
            entered.set()
            await release.wait()
            return "9001"

        first_sender.send_url = send
        first = asyncio.create_task(deliver_pending_once(first_sender))
        await entered.wait()
        await deliver_pending_once(second_sender)
        release.set()
        assert (await first).sent == 1
        assert second_sender.messages == []

    asyncio.run(scenario())


@pytest.mark.parametrize("guild_id,can_send", [(201, True), (200, False)])
def test_bot_refuses_wrong_guild_or_missing_permissions(monkeypatch, guild_id, can_send):
    from types import SimpleNamespace
    from app.services.delivery_errors import DeliveryPermanentError
    client = ScheduleMusicBot()
    channel = SimpleNamespace(
        guild=SimpleNamespace(id=guild_id, me=object()),
        permissions_for=lambda _: SimpleNamespace(view_channel=True, send_messages=can_send),
        send=AsyncMock(),
    )
    monkeypatch.setattr(client, "is_available", lambda: True)
    monkeypatch.setattr(client, "get_channel", lambda _: channel)
    with pytest.raises(DeliveryPermanentError):
        asyncio.run(client.send_url("300", "https://x.com/fixture/status/1", guild_id="200"))
    channel.send.assert_not_awaited()


def test_delivery_loop_runs_while_x_is_blocked(monkeypatch):
    from app.agents import scheduler
    monkeypatch.setattr(scheduler.settings, "agent_run_on_start", True)

    async def scenario():
        x_entered, delivered = asyncio.Event(), asyncio.Event()

        async def collect(**kwargs):
            x_entered.set()
            await asyncio.Event().wait()

        async def deliver(*args):
            await x_entered.wait()
            delivered.set()
            return notification_delivery.DeliveryResult()

        monkeypatch.setattr(scheduler, "collect_x_once", collect)
        monkeypatch.setattr(scheduler, "deliver_pending_once", deliver)
        task = asyncio.create_task(scheduler.agent_loop())
        try:
            await asyncio.wait_for(delivered.wait(), 1)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


def test_route_disabled_during_channel_lookup_is_not_sent(runtime_store, monkeypatch):
    from types import SimpleNamespace
    seed_pending_delivery(runtime_store)
    client = ScheduleMusicBot()
    channel = SimpleNamespace(
        guild=SimpleNamespace(id=200, me=object()),
        permissions_for=lambda _: SimpleNamespace(view_channel=True, send_messages=True),
        send=AsyncMock(),
    )

    async def lookup(_):
        runtime_store.execute("UPDATE notification_routes SET is_active=false")
        runtime_store.commit()
        return channel

    monkeypatch.setattr(client, "is_available", lambda: True)
    monkeypatch.setattr(client, "get_channel", lambda _: None)
    monkeypatch.setattr(client, "fetch_channel", lookup)
    assert asyncio.run(deliver_pending_once(client)).skipped == 1
    channel.send.assert_not_awaited()


@pytest.mark.parametrize("status,expected", [(403, "failed"), (404, "failed"), (429, "retry"), (500, "unknown")])
def test_real_adapter_classifies_http_outcomes(runtime_store, monkeypatch, status, expected):
    import discord
    from types import SimpleNamespace
    seed_pending_delivery(runtime_store)
    client = ScheduleMusicBot()
    response = SimpleNamespace(status=status, reason="test", headers={"Retry-After": "120"})
    exc_type = {403: discord.Forbidden, 404: discord.NotFound}.get(status, discord.HTTPException)
    channel = SimpleNamespace(
        guild=SimpleNamespace(id=200, me=object()),
        permissions_for=lambda _: SimpleNamespace(view_channel=True, send_messages=True),
        send=AsyncMock(side_effect=exc_type(response, "fixture error")),
    )
    monkeypatch.setattr(client, "is_available", lambda: True)
    monkeypatch.setattr(client, "get_channel", lambda _: channel)
    asyncio.run(deliver_pending_once(client))
    assert runtime_store.execute("SELECT status FROM notification_deliveries").fetchone()[0] == expected
    channel.send.assert_awaited_once()


def test_expired_delivery_claim_rejects_late_receipt(runtime_store):
    from app.repositories.runtime_delivery import mark_delivery_sent
    delivery = seed_pending_delivery(runtime_store)
    with notification_delivery.catalog_runtime_session() as session:
        notification_delivery.claim_deliveries(session, worker_id="expired", limit=1)
    runtime_store.execute("UPDATE notification_deliveries SET lease_expires_at=clock_timestamp()-interval '1 second'")
    runtime_store.commit()
    with notification_delivery.catalog_runtime_session() as session:
        assert not mark_delivery_sent(session, delivery, "9001", worker_id="expired")
    sender = RecordingSender()
    assert asyncio.run(deliver_pending_once(sender)).unknown == 1
    assert sender.messages == []


def test_one_shot_delivery_still_runs_when_x_raises(monkeypatch):
    from app.agents import scheduler
    delivery = AsyncMock(return_value=notification_delivery.DeliveryResult())
    monkeypatch.setattr(scheduler, "collect_x_once", AsyncMock(side_effect=RuntimeError("X failed")))
    monkeypatch.setattr(scheduler, "deliver_pending_once", delivery)
    with pytest.raises(RuntimeError, match="X failed"):
        asyncio.run(scheduler.run_agent_once())
    delivery.assert_awaited_once()
