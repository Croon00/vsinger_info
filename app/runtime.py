from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from app.agents.scheduler import agent_loop
from app.api.main import app
from app.bots.discord_bot import start_discord_bot
from app.core.config import settings


async def _serve_api() -> None:
    """Railway가 지정한 PORT에서 FastAPI 서버를 실행합니다."""
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    """API를 실행하고 전환 승인 뒤에만 Discord/수집 runtime을 시작합니다."""
    logging.basicConfig(level=logging.INFO)
    tasks = [_serve_api()]

    if settings.runtime_cutover_enabled:
        tasks.append(start_discord_bot())
        if settings.agent_enabled:
            tasks.append(agent_loop())
        else:
            logging.info("Agent loop is disabled by AGENT_ENABLED=false.")
    else:
        logging.info(
            "Discord and collection runtime are locked by "
            "RUNTIME_CUTOVER_ENABLED=false."
        )

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
