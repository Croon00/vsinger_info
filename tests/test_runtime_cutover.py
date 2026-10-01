"""Deployment guard for the phase-5 runtime cutover."""

from __future__ import annotations

import pytest

from app import runtime


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _record(calls: list[str], name: str) -> None:
    calls.append(name)


@pytest.fixture(autouse=True)
def _no_live_site_monitor(monkeypatch):
    # 로컬 .env가 모니터를 켜 두면 실제 사이트 조회 뒤 24시간 sleep으로 멈춘다.
    monkeypatch.setattr(runtime.settings, "live_site_monitor_enabled", False)
    monkeypatch.setattr(runtime, "live_site_loop", _unexpected_live_site_loop)


async def _unexpected_live_site_loop() -> None:
    raise AssertionError("live_site_loop must not run in runtime cutover tests")


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
    monkeypatch.setattr(runtime, "music_worker_loop", lambda: _record(calls, "music"))

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
    monkeypatch.setattr(runtime, "music_worker_loop", lambda: _record(calls, "music"))

    await runtime.main()

    assert calls == ["api", "discord", "agent", "music"]
