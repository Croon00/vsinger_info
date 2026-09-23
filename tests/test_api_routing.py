"""Canonical API routing without legacy DB writers or external services."""
import importlib

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.main import app


def test_entrypoints_share_app_and_health_does_not_access_db():
    assert importlib.import_module("app.main").app is app
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_catalog_routes_are_canonical_under_api_with_hidden_v2_alias():
    routes = {
        (route.path, frozenset(route.methods)): route
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    canonical = {
        "/api/artists", "/api/search", "/api/concerts",
        "/api/lives/{archive_id}", "/api/albums/{album_id}",
        "/api/recordings/{recording_id}/lyrics",
    }
    assert canonical <= {path for path, _ in routes}
    for path in canonical:
        route = next(route for (candidate, _), route in routes.items() if candidate == path)
        assert route.include_in_schema is True
        alias = next(
            alias for (candidate, _), alias in routes.items()
            if candidate == path.replace("/api/", "/api/v2/", 1)
        )
        assert alias.include_in_schema is False
        assert alias.endpoint is route.endpoint


def test_legacy_write_google_and_provider_routes_are_not_mounted():
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    for removed in (
        "/artists", "/api/auth/google/start", "/api/auth/google/callback",
        "/api/spotify/artists", "/api/youtube-lives", "/api/songs/from-youtube",
    ):
        assert removed not in paths

    client = TestClient(app)
    assert client.post("/api/artists", json={"name": "blocked"}).status_code == 405
    assert client.get("/api/auth/google/start").status_code == 404
