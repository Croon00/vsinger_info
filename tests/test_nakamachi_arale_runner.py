"""Request runner recovery with fake queue results; no DB or provider calls."""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from scripts import register_nakamachi_arale as runner


def test_transient_retry_and_failed_job_do_not_stop_batch(monkeypatch):
    run = AsyncMock(side_effect=[{'id': 1, 'status': 'retry'},
                                {'id': 2, 'status': 'failed'},
                                {'id': 3, 'status': 'succeeded'}, {'status': 'idle'}, {'status': 'idle'}])
    monkeypatch.setattr(runner.music_jobs, 'run_once', run)
    monkeypatch.setattr(runner.music_jobs, 'status', AsyncMock(return_value={'last_error': 'RetryableJobError'}))
    summaries = iter([{'jobs': [{'status': 'retry'}]}, {'jobs': [{'status': 'succeeded'}]}])
    monkeypatch.setattr(runner.backfill, 'status', lambda: next(summaries))
    sleep = AsyncMock()
    monkeypatch.setattr(runner.asyncio, 'sleep', sleep)
    asyncio.run(runner.run_setlist_queue(datetime.now(UTC)))
    assert run.await_count == 5
    assert any(call.args == (30,) for call in sleep.await_args_list)


def test_fresh_quota_error_stops_without_claiming_another_job(monkeypatch):
    run = AsyncMock(return_value={'id': 1, 'status': 'retry'})
    monkeypatch.setattr(runner.music_jobs, 'run_once', run)
    monkeypatch.setattr(runner.music_jobs, 'status', AsyncMock(return_value={'last_error': 'rate_limited'}))
    monkeypatch.setattr(runner.backfill, 'status', lambda: {'jobs': [{'status': 'retry'}]})
    asyncio.run(runner.run_setlist_queue(datetime.now(UTC)))
    assert run.await_count == 1
