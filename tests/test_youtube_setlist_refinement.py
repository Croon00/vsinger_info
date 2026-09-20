import asyncio

from app.integrations import youtube_live_archive
from app.integrations.youtube_live_archive import _performance_values


def test_video_setlist_uses_one_ai_result_when_available(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_extract(comment: str):
        calls.append(comment)
        return [{"timestamp": "01:02", "title": "clean title", "original_artist": "original artist"}]

    monkeypatch.setattr(youtube_live_archive, "extract_youtube_setlist", fake_extract)

    result = asyncio.run(youtube_live_archive._extract_setlist_for_video("START\n01:02 song\nEND"))

    assert calls == ["START\n01:02 song\nEND"]
    assert result == [{"timestamp": "01:02", "title": "clean title", "original_artist": "original artist"}]


def test_replacing_setlist_preserves_known_metadata_at_same_timestamp() -> None:
    old = {
        "song_title_ko": "existing Korean title",
        "original_artist_ko": "existing Korean artist",
        "tj_number": "12345",
        "ky_number": "67890",
        "karaoke_checked_at": "2026-01-01T00:00:00+00:00",
    }

    row = _performance_values(
        7,
        "2026-09-19",
        {"timestamp": "01:02", "title": "clean title", "original_artist": "original artist"},
        {62: old},
    )

    assert row[4:6] == ("clean title", "original artist")
    assert row[6:10] == ("existing Korean title", "existing Korean artist", "12345", "67890")
