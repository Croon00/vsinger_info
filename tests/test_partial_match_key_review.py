"""Partial-link key review on a disposable local PostgreSQL; never reaches Neon."""
import importlib.util
import json
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill, review = load("backfill_song_match_keys"), load("review_partial_match_keys")


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


@pytest.fixture
def partial(database, tmp_path):
    apply_schema(database)
    singer = row(database, "artists", slug="yorushika", name_native="ヨルシカ", entity_kind="group")
    other_artist = row(database, "artists", slug="other", name_native="Other", entity_kind="solo")
    exact = row(database, "songs", title_native="晴る")
    renamed = row(database, "songs", title_native="Butter-Fly (TV size)")
    row(database, "song_artists", song_id=exact, artist_id=singer)
    row(database, "song_artists", song_id=renamed, artist_id=other_artist)
    video = row(database, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive")
    archive = row(database, "live_archives", video_id=video)
    lines = [("晴る", "ヨルシカ", exact), ("「晴る」", "ヨルシカ", None),
             ("Butter-Fly", "和田光司", renamed), ("Butter-Fly", "和田光司", None)]
    for ordinal, (title, artist, song) in enumerate(lines, 1):
        row(database, "performances", archive_id=archive, ordinal=ordinal, start_seconds=ordinal * 10,
            raw_title=title, raw_artist=artist, song_id=song)
    database.commit()
    backfill.apply(database, backfill.plan(backfill.collect(database)))
    database.commit()
    path = tmp_path / "decisions.json"
    data = review.export(database)
    database.rollback()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return database, path, exact, renamed


def entries(path):
    return {e["title_key"]: e for e in json.loads(path.read_text(encoding="utf-8"))["entries"]}


def test_export_prefills_only_exact_matches(partial):
    _, path, exact, renamed = partial
    found = entries(path)
    assert found["晴る"]["decision"] == "confirm" and found["晴る"]["basis"] == "exact"
    assert found["晴る"]["candidate_song_id"] == exact
    fly = found["butter-fly"]
    assert fly["decision"] is None and fly["candidate_song_id"] == renamed
    assert set(fly["review_notes"]) == {"title differs from candidate", "artist differs from candidate"}


def test_apply_stores_decisions_once_and_marks_who_decided(partial):
    conn, path, exact, renamed = partial
    data = json.loads(path.read_text(encoding="utf-8"))
    for e in data["entries"]:
        if e["title_key"] == "butter-fly":
            e["decision"] = "reject"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    decided = review.load(path)
    preview = review.apply(conn, decided, write=False)
    conn.rollback()
    assert preview["status"] == "would_commit" and q(conn, "SELECT count(*) AS n FROM song_match_keys WHERE status='pending'").fetchone()["n"] == 2
    result = review.apply(conn, decided)
    conn.commit()
    assert (result["status"], result["confirmed"], result["rejected"], result["rule_derived"]) == ("committed", 1, 1, 1)
    keys = {r["title_key"]: r for r in q(conn, "SELECT * FROM song_match_keys")}
    assert (keys["晴る"]["status"], keys["晴る"]["song_id"], keys["晴る"]["decided_by"]) == ("confirmed", exact, "existing_link")
    assert (keys["butter-fly"]["status"], keys["butter-fly"]["song_id"], keys["butter-fly"]["decided_by"]) == ("rejected", None, "manual")
    assert review.apply(conn, decided)["status"] == "already_committed"
    conn.rollback()
    # Performances are untouched: linking is a separate step.
    assert q(conn, "SELECT count(*) AS n FROM performances WHERE song_id IS NULL").fetchone()["n"] == 2
    # A later backfill keeps both the manual rejection and the reviewed rule confirmation.
    backfill.apply(conn, backfill.plan(backfill.collect(conn)))
    conn.commit()
    keys = {r["title_key"]: r for r in q(conn, "SELECT * FROM song_match_keys")}
    assert keys["butter-fly"]["status"] == "rejected"
    assert (keys["晴る"]["status"], keys["晴る"]["song_id"]) == ("confirmed", exact)


def test_stale_file_is_refused(partial):
    conn, path, _, _ = partial
    conn.execute("UPDATE song_match_keys SET evidence=evidence || '{\"note\":1}' WHERE title_key='晴る'")
    conn.commit()
    with pytest.raises(RuntimeError, match="re-export"):
        review.apply(conn, review.load(path), write=False)


def test_invalid_decision_is_rejected(partial):
    _, path, _, _ = partial
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"][0]["decision"] = "merge"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid decision"):
        review.load(path)
