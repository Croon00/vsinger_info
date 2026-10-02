"""Shared X provider limits stop a collection pass without touching other accounts."""
import asyncio
from contextlib import contextmanager

from app.repositories.runtime_delivery import XAccount
from app.services import x_collection
from app.integrations.x_client import XProviderUnavailable


def test_provider_limit_pauses_pass_without_failing_accounts(monkeypatch):
    @contextmanager
    def session():
        yield object()

    claimed = []
    paused = []
    failed = []

    def claim(_, *, worker_id, limit, exclude_ids):
        claimed.append(tuple(exclude_ids))
        return [XAccount(1, "42", "fixture", "90", worker_id, True)]

    async def unavailable(*_):
        raise XProviderUnavailable(600)

    monkeypatch.setattr(x_collection, "catalog_runtime_session", session)
    monkeypatch.setattr(x_collection, "claim_x_accounts", claim)
    monkeypatch.setattr(x_collection, "pause_x_account_for_provider",
                        lambda *args, **kwargs: paused.append(kwargs))
    monkeypatch.setattr(x_collection, "fail_x_account",
                        lambda *args, **kwargs: failed.append(kwargs))

    result = asyncio.run(x_collection.collect_x_once(fetch_pages=unavailable, account_limit=5))

    assert claimed == [()]
    assert len(paused) == 1 and paused[0]["retry_after_seconds"] == 600
    assert failed == []
    assert result.accounts == 1 and result.failures == 0
    assert result.provider_wait_seconds == 600
