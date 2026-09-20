"""FastAPI lifecycle, middleware, and router composition."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.artists import router as artists_router
from app.api.routers.auth import router as auth_router
from app.api.routers.read_api import router as frontend_read_router
from app.api.routers.songs import router as songs_router
from app.api.routers.spotify import router as spotify_router
from app.api.routers.youtube import router as youtube_router
from app.core.config import settings
from app.core.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize the legacy schema only when explicitly configured."""
    if settings.database_url and settings.database_auto_init:
        init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """배포된 API 서버가 살아 있는지 확인하는 헬스 체크입니다."""
    return {"status": "ok"}


# Keep both namespaces until existing management clients are retired.
for router in (artists_router, auth_router, songs_router, spotify_router, youtube_router):
    app.include_router(router, prefix="/api")
    app.include_router(router)

app.include_router(frontend_read_router, prefix="/api")
