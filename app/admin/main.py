"""Standalone admin entry point; no legacy runtime or automatic remote migrations."""

from contextlib import asynccontextmanager
import secrets
import time
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import AdminSettings
from .db.local import LocalStore
from .db.remote import RemoteCatalog
from .services.review import ReviewService
from .api.security import LocalGuard, COOKIE
from .api.routes import router_for
from .schemas.catalog import DomainError
from .schemas.contracts import SessionView


def create_app(settings=None, remote=None):
    settings = settings or AdminSettings.load()
    remote = remote or RemoteCatalog(settings.database_url, settings.catalog_instance_id)
    review = ReviewService(LocalStore(settings.workspace), remote, settings.input_dir)
    sessions = {}

    @asynccontextmanager
    async def lifespan(app):
        yield
        if getattr(remote, "engine", None):
            remote.engine.dispose()

    app = FastAPI(
        title="Music Catalog Admin",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.review = review
    app.state.remote = remote
    app.add_middleware(LocalGuard, origins=settings.origins, sessions=sessions)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            {
                "detail": "입력 형식을 확인하세요: "
                + ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
            },
            status_code=422,
        )

    @app.get("/api/admin/session", response_model=SessionView)
    def session(request: Request, response: Response):
        for key in list(sessions):
            if sessions[key]["expires"] < time.time():
                sessions.pop(key, None)
        key = request.cookies.get(COOKIE)
        if key not in sessions:
            if len(sessions) > 1000:
                sessions.clear()
            key = secrets.token_urlsafe(32)
            sessions[key] = {
                "csrf": secrets.token_urlsafe(32),
                "expires": time.time() + 8 * 3600,
            }
        response.set_cookie(
            COOKIE,
            key,
            httponly=True,
            samesite="strict",
            max_age=8 * 3600,
            path="/api/admin",
        )
        return {"csrf": sessions[key]["csrf"]}

    app.include_router(router_for(review, remote))
    if (settings.dist / "assets").is_dir():
        app.mount(
            "/assets", StaticFiles(directory=settings.dist / "assets"), name="assets"
        )

    @app.get("/{path:path}")
    def ui(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "경로를 찾을 수 없습니다."}, status_code=404)
        file = settings.dist / "index.html"
        if not file.exists():
            return JSONResponse(
                {"detail": "admin-web 빌드 후 실행하거나 localhost:5176을 사용하세요."},
                status_code=503,
            )
        return FileResponse(file)

    return app
