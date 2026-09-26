"""song_match_keys backfill on a disposable local PostgreSQL; never reaches Neon."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("backfill_song_match_keys", ROOT / "scripts/backfill_song_match_keys.py")
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)


def run(conn, *, write=True):
    result = backfill.plan(backfill.collect(conn))
    status = backfill.apply(conn, result) if write else None
    conn.commit()
    return result, status


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def keys(conn):
    return {(r["title_key"], r["artist_key"]): r for r in q(conn, "SELECT * FROM song_match_keys")}


@pytest.fixture
def catalog(database):
    apply_schema(database)
    video = row(database, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive")
    archive = row(database, "live_archives", video_id=video)
    lemon, other = row(database, "songs", title_native="Lemon"), row(database, "songs", title_native="Other")
    rows = [
        ("Lemon", "米津玄師", lemon), ("「Lemon」", " 米津玄師", lemon),   # same key, fully linked
        ("晴る", "ヨルシカ", lemon), ("晴る", "ヨルシカ", None),          # partially linked
        ("月光", "鬼束ちひろ", lemon), ("月光", "鬼束ちひろ", other),      # links disagree
        ("こんつきー", None, None), ("「」", None, None),                    # unlinked; empty after normalization, skipped
    ]
    for ordinal, (title, artist, song) in enumerate(rows, 1):
        row(database, "performances", archive_id=archive, ordinal=ordinal, start_seconds=ordinal * 10,
            raw_title=title, raw_artist=artist, song_id=song)
    database.commit()
    return database, lemon, other


def test_backfill_derives_states_from_existing_links_only(catalog):
    conn, lemon, other = catalog
    result, status = run(conn)
    assert status["status"] == "committed"
    assert result["summary"]["skipped_empty_title"] == 1
    found = keys(conn)
    assert set(found) == {("lemon", "米津玄師"), ("晴る", "ヨルシカ"), ("月光", "鬼束ちひろ"), ("こんつきー", "")}
    confirmed = found[("lemon", "米津玄師")]
    assert (confirmed["status"], confirmed["song_id"], confirmed["decided_by"], confirmed["occurrence_count"]) == \
        ("confirmed", lemon, "existing_link", 2)
    partial = found[("晴る", "ヨルシカ")]
    assert partial["status"] == "pending" and partial["song_id"] is None
    assert partial["evidence"] == {"candidate_song_id": lemon, "linked": 1, "unlinked": 1}
    assert found[("月光", "鬼束ちひろ")]["status"] == "ambiguous"
    assert found[("こんつきー", "")]["status"] == "pending"
    # Keys are derived bookkeeping: songs and performances are untouched.
    assert q(conn, "SELECT count(*) AS n FROM performances WHERE song_id IS NULL").fetchone()["n"] == 3
    receipt = q(conn, "SELECT source_kind,result_summary FROM catalog_imports").fetchone()
    assert receipt["source_kind"] == "batch_import" and receipt["result_summary"]["inserts"] == 4


def test_rerun_is_idempotent_and_keeps_manual_decisions(catalog):
    conn, lemon, _ = catalog
    run(conn)
    _, again = run(conn)
    assert again["status"] == "no_changes"
    conn.execute("""UPDATE song_match_keys SET status='not_song',decided_by='manual',decided_at=clock_timestamp()
                    WHERE title_key='こんつきー'""")
    conn.execute("""UPDATE song_match_keys SET status='confirmed',song_id=%s,decided_by='manual',
                    decided_at=clock_timestamp() WHERE title_key='月光'""", (lemon,))
    archive = q(conn, "SELECT id FROM live_archives").fetchone()["id"]
    row(conn, "performances", archive_id=archive, ordinal=9, start_seconds=900, raw_title="こんつきー")
    conn.commit()
    result, status = run(conn)
    assert status["status"] == "committed" and result["summary"]["updates"] == 1
    found = keys(conn)
    assert (found[("こんつきー", "")]["status"], found[("こんつきー", "")]["occurrence_count"]) == ("not_song", 2)
    assert (found[("月光", "鬼束ちひろ")]["status"], found[("月光", "鬼束ちひろ")]["decided_by"]) == ("confirmed", "manual")


def test_auto_state_follows_new_links_and_dry_run_writes_nothing(catalog):
    conn, lemon, _ = catalog
    result, _ = run(conn, write=False)
    assert result["summary"]["inserts"] == 4 and not keys(conn)
    run(conn)
    conn.execute("UPDATE performances SET song_id=%s WHERE raw_title='晴る'", (lemon,))
    conn.commit()
    run(conn)
    partial = keys(conn)[("晴る", "ヨルシカ")]
    assert (partial["status"], partial["song_id"], partial["decided_by"]) == ("confirmed", lemon, "existing_link")


def test_requires_revision_004(database):
    apply_schema(database)
    database.execute("DELETE FROM catalog_schema_migrations WHERE version='004'")
    with pytest.raises(RuntimeError, match="revision 004"):
        backfill.check_target(database)
