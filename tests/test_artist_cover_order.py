from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.read_api import catalog, router
from app.core.config import settings
from app.repositories.catalog_read import CatalogReadRepository


def test_cover_order_is_validated_passed_through_and_returns_view_counts(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix='/api')
    calls = []

    def covers(artist_id, offset, limit, order='latest'):
        calls.append((artist_id, offset, limit, order))
        return dict(items=[dict(id=1, youtube_video_id='abcdefghijk', youtube_url='https://www.youtube.com/watch?v=abcdefghijk',
                                title='Song cover', published_at=None, duration_seconds=200, view_count=0,
                                views_updated_at=None)], total=1, offset=offset, limit=limit)

    app.dependency_overrides[catalog] = lambda: SimpleNamespace(
        query_ms=0, query_count=0, covers=covers, artist=lambda artist_id: dict(id=artist_id))
    monkeypatch.setattr(settings, 'api_key', 'fixture')
    with TestClient(app, headers={'X-API-Key': 'fixture'}) as client:
        response = client.get('/api/artists/7/covers')
        assert response.status_code == 200, response.text
        assert calls[-1] == (7, 0, 12, 'latest')
        assert response.json()['items'][0]['view_count'] == 0  # zero is a real count, not unknown
        for order in ['latest', 'oldest', 'views']:
            assert client.get(f'/api/artists/7/covers?order={order}&offset=12').status_code == 200
            assert calls[-1] == (7, 12, 12, order)
        assert client.get('/api/artists/7/covers?order=high').status_code == 422


def test_cover_orders_put_unknown_views_last_and_break_ties():
    orders = CatalogReadRepository.COVER_ORDERS
    assert set(orders) == {'latest', 'oldest', 'views'}
    assert orders['views'].startswith('q.view_count DESC NULLS LAST')
    assert all(order.endswith(('q.id DESC', 'q.id')) for order in orders.values())
