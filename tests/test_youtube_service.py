import asyncio
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from app.api.routers import youtube as youtube_router
from app.core.security import require_api_key
from app.services.youtube_service import YouTubeService


def test_all_artist_records_are_not_capped_at_100():
    rows = [{"id": i} for i in range(267)]
    with patch('app.services.youtube_service.list_youtube_live_archives', return_value=rows) as query:
        assert len(YouTubeService().list_lives(100, 'HACHI', all_records=True)) == 267
        query.assert_called_once_with(limit=None, artist_name='HACHI')


def test_global_requests_remain_bounded():
    with patch('app.services.youtube_service.list_youtube_live_archives', return_value=[]) as query:
        YouTubeService().list_lives(500, None, all_records=True)
        query.assert_called_once_with(limit=100, artist_name=None)


def test_channel_backfill_awaits_integration_and_returns_stats():
    stats = {"videos_found": 2, "archives_saved": 2, "setlists_found": 1, "failed": 0}
    with patch('app.services.youtube_service.backfill_youtube_channel', autospec=True, return_value=stats) as collect:
        result = asyncio.run(YouTubeService().backfill_channel('https://www.youtube.com/@HACHIVSinger', 'HACHI'))

    assert result == stats
    collect.assert_awaited_once_with(channel_url='https://www.youtube.com/@HACHIVSinger', artist_name='HACHI')


def test_backfill_endpoint_runs_collection_after_accepting_request(monkeypatch):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        completed = asyncio.Event()
        tasks = set()

        async def collect(*, channel_url, artist_name):
            assert channel_url == 'https://www.youtube.com/@HACHIVSinger'
            assert artist_name == 'HACHI'
            started.set()
            await release.wait()
            completed.set()
            return {"videos_found": 1, "archives_saved": 1, "setlists_found": 1, "failed": 0}

        monkeypatch.setattr('app.services.youtube_service.backfill_youtube_channel', collect)
        monkeypatch.setattr(youtube_router, '_backfill_tasks', tasks)
        app = FastAPI()
        app.include_router(youtube_router.router)
        app.dependency_overrides[require_api_key] = lambda: None

        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await asyncio.wait_for(client.post('/youtube-lives/backfills', json={
                    'channel_url': 'https://www.youtube.com/@HACHIVSinger',
                    'artist_name': 'HACHI',
                }), timeout=2)

            assert response.status_code == 202
            assert response.json() == {"status": "accepted"}
            await asyncio.wait_for(started.wait(), timeout=2)
            assert len(tasks) == 1
            assert not completed.is_set()
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
            assert completed.is_set()
            assert not tasks
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())
