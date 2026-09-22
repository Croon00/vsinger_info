"""Deployment guard for the phase-5 runtime cutover."""

from __future__ import annotations

import pytest

from app import runtime


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _record(calls: list[str], name: str) -> None:
    calls.append(name)


@pytest.mark.anyio
async def test_runtime_starts_only_api_before_cutover(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runtime.settings, "runtime_cutover_enabled", False)
    monkeypatch.setattr(runtime.settings, "agent_enabled", True)
    monkeypatch.setattr(runtime, "_serve_api", lambda: _record(calls, "api"))
    monkeypatch.setattr(
        runtime, "start_discord_bot", lambda: _record(calls, "discord")
    )
    monkeypatch.setattr(runtime, "agent_loop", lambda: _record(calls, "agent"))

    await runtime.main()

    assert calls == ["api"]


@pytest.mark.anyio
async def test_runtime_starts_discord_and_agent_after_cutover(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runtime.settings, "runtime_cutover_enabled", True)
    monkeypatch.setattr(runtime.settings, "agent_enabled", True)
    monkeypatch.setattr(runtime, "_serve_api", lambda: _record(calls, "api"))
    monkeypatch.setattr(
        runtime, "start_discord_bot", lambda: _record(calls, "discord")
    )
    monkeypatch.setattr(runtime, "agent_loop", lambda: _record(calls, "agent"))

    await runtime.main()

    assert calls == ["api", "discord", "agent"]
