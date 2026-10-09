"""DB-free idle waits aligned across workers to leave room for scale to zero."""
import asyncio
import time
from datetime import UTC, datetime

from app.core.config import settings


def idle_delay() -> float:
    interval = settings.worker_idle_seconds
    return interval - time.time() % interval


async def wait_for_work(*, seconds=None, wake=None, health=None):
    # Use a monotonic deadline once scheduled; wall-clock adjustments cannot
    # stretch the sleep. Heartbeats describe process health, not DB traffic.
    delay = idle_delay() if seconds is None else max(0, seconds)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + delay
    while True:
        if health is not None:
            health['heartbeat_at'] = datetime.now(UTC).isoformat()
        remaining = deadline - loop.time()
        if remaining <= 0:
            return
        step = min(30, remaining)
        if wake is None:
            await asyncio.sleep(step)
        else:
            try:
                await asyncio.wait_for(wake.wait(), timeout=step)
                return
            except TimeoutError:
                pass
