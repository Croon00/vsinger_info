"""Linking performances through confirmed match keys, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("link", ROOT / "scripts/link_performances_from_match_keys.py")
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def key(conn, title, artist, status="pending", song=None):
    decided = status != "pending"
    return row(conn, "song_match_keys", title_key=title, artist_key=artist, status=status, song_id=song,
               sample_raw_title=title, decided_by="manual" if decided else None,
               decided_at="2026-09-27T00:00:00Z" if decided else None)


@pytest.fixture
def catalog(database):
    apply_schema(database)
    lemon, merged, archived = (row(database, "songs", title_native=t) for t in ("Lemon", "Old", "Gone"))
    target = row(database, "songs", title_native="New")
    database.execute("UPDATE songs SET archived_at=clock_timestamp() WHERE id=%s", (archived,))
    row(database, "song_merges", source_song_id=merged, target_song_id=target, reason="duplicate")
    key(database, "lemon", "米津玄師", "confirmed", lemon)
    key(database, "old", "", "confirmed", merged)
    key(database, "gone", "", "confirmed", archived)
    key(database, "pending", "")
    video = row(database, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive")
    archive = row(database, "live_archives", video_id=video)
    lines = [("「Lemon」", "米津玄師", None), ("LEMON", " 米津玄師", None), ("Lemon", "米津玄師", target),
             ("Lemon", None, None), ("Old", None, None), ("Gone", None, None), ("pending", None, None)]
    for ordinal, (title, artist, song) in enumerate(lines, 1):
        row(database, "performances", archive_id=archive, ordinal=ordinal, start_seconds=ordinal * 10,
            raw_title=title, raw_artist=artist, song_id=song)
    database.commit()
    database.autocommit = True
    return database, lemon, target


def test_dry_run_plans_without_writing(catalog):
    conn, _, _ = catalog
    result = link.run(conn, write=False)
    assert (result["links"], result["unlinked_performances"], result["still_unlinked"]) == (2, 6, 4)
    assert q(conn, "SELECT count(*) AS n FROM performances WHERE song_id IS NULL").fetchone()["n"] == 6


def test_apply_links_only_exact_confirmed_keys_with_audit(catalog):
    conn, lemon, target = catalog
    result = link.run(conn, write=True)
    assert (result["linked"], result["bucket_status"]) == (2, {"committed": 1})
    by_title = {(r["raw_title"], r["raw_artist"]): r["song_id"] for r in q(conn, "SELECT * FROM performances")}
    assert by_title[("「Lemon」", "米津玄師")] == lemon and by_title[("LEMON", " 米津玄師")] == lemon
    assert by_title[("Lemon", "米津玄師")] == target            # existing link untouched
    assert by_title[("Lemon", None)] is None                   # different key (no artist)
    assert by_title[("Old", None)] is None and by_title[("Gone", None)] is None  # merged / archived song skipped
    assert by_title[("pending", None)] is None
    changes = q(conn, "SELECT * FROM catalog_changes WHERE entity_type='performances'").fetchall()
    assert len(changes) == 2 and all(c["after_data"] == {"song_id": lemon} and c["before_data"] == {"song_id": None}
                                     for c in changes)
    assert q(conn, "SELECT source_kind FROM catalog_imports").fetchone()["source_kind"] == "correction"
    again = link.run(conn, write=True)
    assert (again["links"], again["linked"]) == (0, 0)


def test_concurrent_change_rolls_back_bucket(catalog, monkeypatch):
    conn, _, _ = catalog
    original = link.collect

    def stale(c):
        planned = original(c)
        for links in planned["buckets"].values():
            links[0]["version"] += 1
        return planned

    monkeypatch.setattr(link, "collect", stale)
    with pytest.raises(RuntimeError, match="changed since planning"):
        link.run(conn, write=True)
    assert q(conn, "SELECT count(*) AS n FROM performances WHERE song_id IS NULL").fetchone()["n"] == 6
    assert q(conn, "SELECT count(*) AS n FROM catalog_imports").fetchone()["n"] == 0



def test_combined_title_artist_line_links_through_confirmed_split_key(catalog):
    conn, lemon, _ = catalog
    archive = q(conn, "SELECT id FROM live_archives").fetchone()["id"]
    row(conn, "performances", archive_id=archive, ordinal=8, start_seconds=80, raw_title="Lemon  /  米津玄師")
    row(conn, "performances", archive_id=archive, ordinal=9, start_seconds=90, raw_title="Lemon / 米津玄師", raw_artist="x")
    assert link.run(conn, write=True)["linked"] == 3
    linked = {r["ordinal"]: r["song_id"] for r in q(conn, "SELECT ordinal, song_id FROM performances WHERE ordinal>7")}
    assert linked == {8: lemon, 9: None}   # a given raw artist disables splitting
    matches = [c["provenance"]["match"] for c in q(conn, "SELECT provenance FROM catalog_changes ORDER BY entity_id")]
    assert matches == ["exact", "exact", "split"]