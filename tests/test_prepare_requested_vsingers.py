import asyncio
import json

from scripts import prepare_requested_vsingers as module
from app.integrations.youtube_catalog import YouTubeFailure


def test_listing_deduplicates_and_records_truncation(tmp_path, monkeypatch):
    class Provider:
        def __init__(self, key):
            pass

        async def get(self, resource, **params):
            if resource == "channels":
                return {"items": [{"id": "channel", "snippet": {"title": "Singer"},
                                   "contentDetails": {"relatedPlaylists": {"uploads": "uploads"}}}]}
            return {"items": [
                {"snippet": {"title": "Singing", "videoOwnerChannelId": "channel"},
                 "contentDetails": {"videoId": "one"}},
                {"snippet": {"title": "Singing"}, "contentDetails": {"videoId": "one"}},
                {"snippet": {"title": "Singing", "videoOwnerChannelId": "other"},
                 "contentDetails": {"videoId": "other"}},
            ], "nextPageToken": "more"}

    monkeypatch.setattr(module, "YouTubeClient", Provider)
    seed = {"artists": [{"slug": "singer", "channel_url": "https://www.youtube.com/@singer"}]}
    assert asyncio.run(module.research(seed, tmp_path, 1)) == 0
    result = json.loads((tmp_path / "singer.json").read_text(encoding="utf-8"))
    assert result["listed_videos"] == result["singing_candidates"] == 1
    assert result["listing_complete"] is False


def test_quota_stops_before_next_channel_and_keeps_safe_reason(tmp_path, monkeypatch):
    class Provider:
        def __init__(self, key):
            pass

        async def get(self, resource, **params):
            raise YouTubeFailure("quotaExceeded", retry=True, retry_after=86400)

    monkeypatch.setattr(module, "YouTubeClient", Provider)
    seed = {"artists": [{"slug": slug, "channel_url": "https://www.youtube.com/@" + slug}
                        for slug in ("first", "second")]}
    assert asyncio.run(module.research(seed, tmp_path, 1)) == 1
    result = json.loads((tmp_path / "first.json").read_text(encoding="utf-8"))
    assert result["reason"] == "quotaExceeded"
    assert not (tmp_path / "second.json").exists()


def test_channel_id_mismatch_is_not_accepted(tmp_path, monkeypatch):
    class Provider:
        def __init__(self, key):
            pass

        async def get(self, resource, **params):
            return {"items": [{"id": "other", "snippet": {"title": "Other artist"}}]}

    monkeypatch.setattr(module, "YouTubeClient", Provider)
    seed = {"artists": [{"slug": "singer", "channel_url": "https://www.youtube.com/channel/requested"}]}
    assert asyncio.run(module.research(seed, tmp_path, 0)) == 1
    result = json.loads((tmp_path / "singer.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["reason"] == "channel_mismatch"
    assert "channel_id" not in result
