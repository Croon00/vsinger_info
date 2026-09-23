"""Local PostgreSQL smoke test for legacy setlist batch writes and retry."""
import importlib.util
from pathlib import Path
import sys

from test_catalog_migration import local_server, database, apply, row


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("legacy_import", ROOT / "scripts/import_legacy_setlists.py")
legacy_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy_import)
sys.path.insert(0, str(ROOT / "scripts"))
import correct_legacy_group_live_hosts as group_correction
import backfill_performance_hosts as singer_backfill


def test_batch_insert_and_idempotent_retry(database):
    apply(database)
    artist_id = row(database, "artists", slug="solo", name_native="Singer", entity_kind="solo")
    account_id = row(database, "external_accounts", platform="youtube",
                     platform_id="UCtestchannel", url="https://www.youtube.com/channel/UCtestchannel")
    database.commit()
    catalog_id = str(database.execute("SELECT id FROM catalog_instance").fetchone()[0])
    database.commit()
    item = {
        "legacy_archive_id": 91,
        "video_id": "AaBbCcDdE01",
        "video_title": "Old singing stream",
        "published_at": "2024-01-01 00:00:00+00",
        "broadcast_at": None,
        "duration_seconds": 3600,
        "top_comment": "0:10 First song / Artist",
        "source_account_id": account_id,
        "primary_artist_id": artist_id,
        "evidence": {"performer": artist_id, "channel_owner": None, "x_author": None},
        "performances": [
            {"legacy_performance_id": 501, "ordinal": 1, "start_seconds": 10,
             "raw_title": "First song", "raw_artist": "Artist", "raw_timestamp": "0:10"},
            {"legacy_performance_id": 502, "ordinal": 2, "start_seconds": 20,
             "raw_title": "Second song", "raw_artist": None, "raw_timestamp": "0:20"},
        ],
    }
    assert legacy_import.apply_bucket(database, 0, [item], catalog_id) == "committed"
    assert legacy_import.apply_bucket(database, 0, [item], catalog_id) == "already_committed"
    assert database.execute("SELECT count(*) FROM videos").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM live_archives").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM performances").fetchone()[0] == 2
    assert database.execute("SELECT count(*) FROM archive_artists").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM archive_sources").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM catalog_changes").fetchone()[0] == 7
    assert database.execute("SELECT source_account_id FROM videos").fetchone()[0] == account_id
    mapping = database.execute("SELECT result_mapping FROM catalog_imports").fetchone()[0]
    assert {entry["legacy_id"] for entry in mapping} == {91, 501, 502}
    database.execute("UPDATE videos SET source_account_id=NULL")  # Simulate the initial importer bug.
    database.commit()
    assert legacy_import.repair_source_accounts(database, 0, [item], catalog_id) == "corrected"
    assert legacy_import.repair_source_accounts(database, 0, [item], catalog_id) == "already_corrected"
    assert database.execute("SELECT source_account_id FROM videos").fetchone()[0] == account_id
    assert database.execute("SELECT count(*) FROM catalog_changes").fetchone()[0] == 8


def test_duplicate_selection_keeps_only_a_proven_superset():
    def song(second, title):
        return {"start_seconds": str(second), "song_title": title,
                "original_artist": None, "timestamp_text": str(second)}

    short = {"id": "1", "top_comment": "same comment",
             "duration_seconds": None, "broadcast_at": None}
    long = {"id": "2", "top_comment": "same comment",
            "duration_seconds": None, "broadcast_at": None}
    conflicting = {"id": "3", "top_comment": "same comment",
                   "duration_seconds": None, "broadcast_at": None}
    legacy = {
        "groups": {"nested": [short, long], "conflict": [short, conflicting]},
        "performances": {1: [song(10, "A")],
                         2: [song(10, "A"), song(20, "B")],
                         3: [song(10, "Different")]},
    }
    chosen, details = legacy_import.safe_duplicate_selections(legacy)
    assert chosen == {2}
    assert details[0]["collapsed_archive_ids"] == [1]


def test_group_host_correction_keeps_archive_link_consistent(database):
    apply(database)
    group_id = row(database, "artists", slug="kmnz", name_native="KMNZ", entity_kind="group")
    member_id = row(database, "artists", slug="kmnz-tina", name_native="TINA", entity_kind="solo")
    database.execute("INSERT INTO artist_group_members(group_id,member_id) VALUES (%s,%s)",
                     (group_id, member_id))
    video_id = row(database, "videos", platform="youtube", platform_video_id="AaBbCcDdE02",
                   title="#KMNZTINA singing stream")
    archive_id = row(database, "live_archives", video_id=video_id, primary_artist_id=group_id)
    link_id = row(database, "archive_artists", archive_id=archive_id,
                  artist_id=group_id, role="host")
    database.commit()
    catalog_id = str(database.execute("SELECT id FROM catalog_instance").fetchone()[0])
    database.commit()
    candidates = [{"legacy_archive_id": 91, "video_id": "AaBbCcDdE02",
                   "archive_id": archive_id, "archive_artist_id": link_id,
                   "from_artist_id": group_id, "to_artist_id": member_id,
                   "title_rule": "kmnz-tina"}]
    assert group_correction.apply(database, candidates, catalog_id) == "corrected"
    assert group_correction.apply(database, candidates, catalog_id) == "already_corrected"
    assert database.execute("SELECT primary_artist_id FROM live_archives").fetchone()[0] == member_id
    assert database.execute("SELECT artist_id FROM archive_artists").fetchone()[0] == member_id
    assert database.execute("SELECT count(*) FROM catalog_changes").fetchone()[0] == 2


def test_provisional_host_singer_links_are_audited_and_retry_safe(database):
    apply(database)
    artist_id = row(database, "artists", slug="host", name_native="Host", entity_kind="solo")
    video_id = row(database, "videos", platform="youtube", platform_video_id="AaBbCcDdE03",
                   title="Live")
    archive_id = row(database, "live_archives", video_id=video_id, primary_artist_id=artist_id)
    row(database, "archive_artists", archive_id=archive_id, artist_id=artist_id, role="host")
    first_id = row(database, "performances", archive_id=archive_id, ordinal=1,
                   start_seconds=10, raw_title="One")
    second_id = row(database, "performances", archive_id=archive_id, ordinal=2,
                    start_seconds=20, raw_title="Two")
    database.commit()
    catalog_id = str(database.execute("SELECT id FROM catalog_instance").fetchone()[0])
    database.commit()
    entries = [(first_id, artist_id), (second_id, artist_id)]
    assert singer_backfill.apply_bucket(database, catalog_id, 0, entries) == ("committed", 2)
    assert singer_backfill.apply_bucket(database, catalog_id, 0, entries) == ("already_committed", 0)
    assert database.execute("SELECT count(*) FROM performance_artists WHERE artist_id=%s",
                            (artist_id,)).fetchone()[0] == 2
    assert database.execute("SELECT count(*) FROM catalog_changes WHERE entity_type='performance_artists'").fetchone()[0] == 2
