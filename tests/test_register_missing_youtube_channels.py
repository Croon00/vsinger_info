import asyncio
from unittest.mock import AsyncMock, MagicMock

from scripts import register_missing_youtube_channels as registration
from scripts.register_missing_youtube_channels import registration_action


def test_native_artist_and_latin_monitor_are_the_same_registration():
    assert registration_action(
        {"artist_name": "花譜"},
        [{"name": "kaf"}],
        [{"artist_name": "KAF", "youtube_channel_id": "channel", "is_active": True}],
    ) == "already_registered"


def test_shared_group_channel_does_not_create_a_second_monitor():
    assert registration_action(
        {"artist_name": "KMNZ LITA"},
        [{"name": "KMNZ LITA"}],
        [{"artist_name": "KMNZ", "youtube_channel_id": "shared", "is_active": True}],
        channel_id="shared",
    ) == "already_registered"


def test_disabled_monitor_is_preserved():
    assert registration_action(
        {"artist_name": "CIEL"},
        [{"name": "CIEL"}],
        [{"artist_name": "CIEL", "youtube_channel_id": "channel", "is_active": False}],
    ) == "disabled"


def test_only_registered_artists_with_missing_monitors_are_added():
    entry = {"artist_name": "CIEL"}
    assert registration_action(entry, [], []) == "missing_artist"
    assert registration_action(entry, [{"name": "CIEL"}], []) == "register"


def test_preview_resolves_channel_without_writing_and_apply_is_repeatable(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.side_effect = [
        [{"name": "CIEL"}], [],
        [{"name": "CIEL"}], [],
        [{"name": "CIEL"}], [
            {"artist_name": "CIEL", "youtube_channel_id": "channel", "is_active": True}
        ],
    ]
    monkeypatch.setattr(registration, "get_connection", lambda: connection)
    resolve = AsyncMock(return_value={
        "youtube_channel_id": "channel", "channel_url": "https://www.youtube.com/@CIEL",
        "channel_title": "CIEL",
    })
    create = AsyncMock(return_value={"id": 42})
    monkeypatch.setattr(registration, "resolve_youtube_channel", resolve)
    monkeypatch.setattr(registration, "create_youtube_channel_monitor", create)
    entries = [{"artist_name": "CIEL", "channel_url": "https://www.youtube.com/@CIEL",
                "source_url": "https://kamitsubaki.jp/artist/ciel/"}]

    result = asyncio.run(registration.register_missing(entries, apply=False, owner="system:catalogue"))
    assert result[0]["status"] == "would_register"
    create.assert_not_called()
    result = asyncio.run(registration.register_missing(entries, apply=True, owner="system:catalogue"))
    assert result[0]["status"] == "registered"
    assert result[0]["monitor_id"] == 42
    result = asyncio.run(registration.register_missing(entries, apply=True, owner="system:catalogue"))
    assert result[0]["status"] == "already_registered"
    create.assert_awaited_once()


def test_channel_failure_does_not_block_next_artist_or_expose_provider_url(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.side_effect = [[{"name": "CIEL"}, {"name": "ASU"}], []]
    monkeypatch.setattr(registration, "get_connection", lambda: connection)
    monkeypatch.setattr(registration, "resolve_youtube_channel", AsyncMock(side_effect=[
        RuntimeError("https://provider.invalid/?key=secret"),
        {"youtube_channel_id": "asu", "channel_url": "https://www.youtube.com/@ASU", "channel_title": "ASU"},
    ]))
    entries = [{"artist_name": name, "channel_url": f"https://www.youtube.com/@{name}",
                "source_url": "https://kamitsubaki.jp/"} for name in ("CIEL", "ASU")]
    result = asyncio.run(registration.register_missing(entries, apply=False, owner="system:catalogue"))
    assert [row["status"] for row in result] == ["failed", "would_register"]
    assert result[0]["error_type"] == "RuntimeError"
    assert "secret" not in str(result)
