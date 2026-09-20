"""Routing compatibility without live databases or external services."""

import importlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routers import auth, spotify


@pytest.mark.parametrize("domain", ["auth", "spotify"])
def test_router_can_be_imported_before_application(domain):
    # A fresh interpreter catches the old router -> main -> router import cycle.
    result = subprocess.run(
        [sys.executable, "-c", f"import app.api.routers.{domain}; import app.api.main"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_entrypoints_share_the_same_app_and_health_does_not_access_db():
    assert importlib.import_module("app.main").app is app
    # Do not enter the lifespan: this check must not run configured DB startup.
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_legacy_routes_keep_prefixed_aliases_and_contracts():
    routes = {
        (route.path, frozenset(route.methods)): route
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert {
        "/artists", "/auth/google/start", "/songs/from-youtube",
        "/spotify/artists", "/youtube-lives",
    } <= {path for path, _ in routes}
    for (path, methods), route in routes.items():
        if path == "/health" or path.startswith("/api/"):
            continue
        alias = routes[(f"/api{path}", methods)]
        assert route.endpoint is alias.endpoint
        assert route.status_code == alias.status_code
        assert route.response_model == alias.response_model
        assert [dep.call for dep in route.dependant.dependencies] == [
            dep.call for dep in alias.dependant.dependencies
        ]


@pytest.mark.parametrize("prefix", ["", "/api"])
def test_google_routes_use_domain_handlers(monkeypatch, prefix):
    monkeypatch.setattr(auth, "google_oauth_configured", lambda: True)
    monkeypatch.setattr(
        auth, "build_google_auth_url", lambda user: f"https://example.test/oauth?state={user}"
    )
    exchange = AsyncMock()
    monkeypatch.setattr(auth, "exchange_code_for_tokens", exchange)
    client = TestClient(app)

    redirect = client.get(f"{prefix}/auth/google/start?discord_user_id=123", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.test/oauth?state=123"
    callback = client.get(f"{prefix}/auth/google/callback?code=test-code&state=123")
    assert callback.status_code == 200
    assert callback.headers["content-type"].startswith("text/html")
    exchange.assert_awaited_once_with("test-code", "123")


@pytest.mark.parametrize("prefix", ["", "/api"])
def test_spotify_routes_use_domain_handlers(monkeypatch, prefix):
    monkeypatch.setattr(spotify, "spotify_configured", lambda: False)
    response = TestClient(app).get(f"{prefix}/spotify/albums/example")
    assert response.status_code == 503
    assert response.json() == {"detail": "Spotify API가 설정되어 있지 않습니다."}
