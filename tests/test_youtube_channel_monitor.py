import pytest
import asyncio
import httpx

from app.integrations import youtube_channel_monitor as monitor

from app.integrations.youtube_channel_monitor import (
    _channel_locator,
    _is_singing_stream_title,
    _performer_for_singing_stream,
)
from app.integrations.youtube_channel_monitor import _is_cover_video


def test_channel_fetch_only_returns_completed_live_archives(monkeypatch) -> None:
    start = "2026-08-01T10:00:00Z"
    end = "2026-08-01T11:00:00Z"
    videos = [
        {"id": "archive", "liveStreamingDetails": {"actualStartTime": start, "actualEndTime": end}},
        {"id": "short"},
        {"id": "upload", "liveStreamingDetails": {}},
        {"id": "upcoming", "liveStreamingDetails": {"scheduledStartTime": start}},
        {"id": "live", "liveStreamingDetails": {"actualStartTime": start}},
        {"id": "incomplete", "liveStreamingDetails": {"actualEndTime": end}},
    ]
    for video in videos:
        video["snippet"] = {"title": "【歌枠】 " + video["id"]}

    def respond(request):
        if request.url.path.endswith("/playlistItems"):
            return httpx.Response(200, json={"items": [
                {"contentDetails": {"videoId": video["id"]}, "snippet": video["snippet"]}
                for video in videos
            ]})
        assert request.url.path.endswith("/videos")
        assert "liveStreamingDetails" in request.url.params["part"]
        return httpx.Response(200, json={"items": videos})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(monitor.httpx, "AsyncClient", lambda **kwargs: client_class(
        **kwargs, transport=httpx.MockTransport(respond)
    ))
    result = asyncio.run(monitor._fetch_recent_singing_streams("uploads"))
    assert [video["youtube_video_id"] for video in result] == ["archive"]
    assert result[0]["actual_end_at"].isoformat() == "2026-08-01T11:00:00+00:00"


def test_channel_locator_supports_handle_and_channel_id_urls() -> None:
    assert _channel_locator("https://www.youtube.com/@HACHIVSinger") == (
        "handle", "HACHIVSinger"
    )
    assert _channel_locator(
        "https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa"
    ) == ("id", "UCaaaaaaaaaaaaaaaaaaaaaa")


def test_channel_locator_rejects_video_and_custom_urls() -> None:
    with pytest.raises(ValueError):
        _channel_locator("https://www.youtube.com/watch?v=abcdefghijk")


def test_cover_video_detection_uses_title_or_description() -> None:
    assert _is_cover_video("【歌ってみた】테스트")
    assert _is_cover_video("새 영상", "A new COVER is here")
    assert not _is_cover_video("오리지널 싱글 공개")


@pytest.mark.parametrize(
    "title",
    [
        "【歌枠】RIOT MUSIC singing relay",
        "KARAOKE STREAM - archive",
        "弾き語り live",
        "Singing Stream with chat",
    ],
)
def test_singing_stream_title_keywords_match(title: str) -> None:
    assert _is_singing_stream_title(title)


def test_singing_stream_title_keywords_reject_non_music_upload() -> None:
    assert not _is_singing_stream_title("weekly schedule and chat announcement")


def test_vesperbell_singing_streams_are_attributed_by_member_credit() -> None:
    assert _performer_for_singing_stream(
        "VESPERBELL", "【歌枠】title【VESPERBELL ヨミ】"
    ) == "VESPERBELL YOMI"
    assert _performer_for_singing_stream(
        "VESPERBELL", "【歌枠】title【VESPERBELL カスカ】"
    ) == "VESPERBELL KASUKA"
    assert _performer_for_singing_stream(
        "VESPERBELL", "【歌枠】title【#ヨミネロ】"
    ) == "VESPERBELL YOMI"
    assert _performer_for_singing_stream(
        "VESPERBELL", "【歌枠】title【#カスカコラボ】"
    ) == "VESPERBELL KASUKA"
    assert _performer_for_singing_stream("VESPERBELL", "【歌枠】duo stream") == "VESPERBELL"
    assert _performer_for_singing_stream("Enma_Ruri", "【歌枠】anything ヨミ") == "Enma_Ruri"


def test_kmnz_singing_streams_are_attributed_by_member_hashtag() -> None:
    assert _performer_for_singing_stream("KMNZ", "【歌枠】title #KMNZLITA") == "KMNZ LITA"
    assert _performer_for_singing_stream("KMNZ", "【歌枠】title【#KMNZNERO】") == "KMNZ NERO"
    assert _performer_for_singing_stream("KMNZ", "【歌枠】title #KMNZTINA") == "KMNZ TINA"
    assert _performer_for_singing_stream("KMNZ", "【歌枠】group stream #KMNZ") == "KMNZ"
