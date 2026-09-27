"""Catalog corrections found in the 2026-09-27 title_ko review, on a disposable local PostgreSQL.

HACHI (VTuber) and ハチ (Vocaloid producer, name_latin "Hachi") are different artists:
the setlist spelling "HACHI" must resolve to HACHI only, and a wrong credit can be removed.
"""
import importlib.util
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


credits = load("remove_song_credits")
matcher = load("match_song_candidates")
wd = load("wikidata_title_ko")


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


@pytest.fixture
def catalog(database):
    apply_schema(database)
    hachi = row(database, "artists", slug="hachi", name_native="HACHI", name_ko="하치", entity_kind="solo")
    vocalo = row(database, "artists", slug="hachi-p", name_native="ハチ", name_latin="Hachi", name_ko="하치", entity_kind="solo")
    firefly, sand = row(database, "songs", title_native="八月の蛍"), row(database, "songs", title_native="砂の惑星")
    row(database, "song_artists", song_id=firefly, artist_id=hachi, position=0)
    row(database, "song_artists", song_id=firefly, artist_id=vocalo, position=1)
    row(database, "song_artists", song_id=sand, artist_id=vocalo, position=0)
    row(database, "song_match_keys", title_key="rainy proof", artist_key="hachi", sample_raw_title="Rainy proof",
        sample_raw_artist="HACHI", occurrence_count=3)
    row(database, "song_match_keys", title_key="砂の惑星", artist_key="はち", sample_raw_title="砂の惑星",
        sample_raw_artist="はち", occurrence_count=2)
    database.commit()
    return database, {"hachi": hachi, "vocalo": vocalo, "firefly": firefly, "sand": sand}


def test_native_name_beats_romanized_name(catalog):
    conn, ids = catalog
    data = matcher.load(conn, keys=10, songs=False)
    conn.rollback()
    by_title = {t.title: t for t in data["targets"]}
    assert list(by_title["Rainy proof"].our_artist_ids) == [ids["hachi"]]   # not also ハチ via "Hachi"


def removal(ids, *pairs):
    return {"policy": credits.POLICY,
            "removals": [{"song_id": ids[s], "artist_id": ids[a], "reason": "different artist"} for s, a in pairs]}


def test_remove_credit_once_with_audit(catalog):
    conn, ids = catalog
    decisions = removal(ids, ("firefly", "vocalo"))
    dry = credits.apply(conn, decisions, write=False)
    conn.rollback()
    assert dry["status"] == "would_commit" and dry["songs"] == [
        {"song_id": ids["firefly"], "removed": [ids["vocalo"]], "kept": [ids["hachi"]]}]
    result = credits.apply(conn, decisions, write=True)
    conn.commit()
    assert result["status"] == "committed"
    assert [r["artist_id"] for r in q(conn, "SELECT artist_id FROM song_artists WHERE song_id=%s", (ids["firefly"],))] == [ids["hachi"]]
    assert q(conn, "SELECT count(*) AS n FROM song_artists WHERE song_id=%s", (ids["sand"],)).fetchone()["n"] == 1
    change = q(conn, "SELECT entity_type, action, before_data, after_data FROM catalog_changes").fetchone()
    assert (change["entity_type"], change["action"], change["after_data"]) == ("song_artists", "delete", None)
    assert change["before_data"]["artist_id"] == ids["vocalo"]
    assert credits.apply(conn, decisions, write=True)["status"] == "already_committed"
    conn.rollback()


def test_remove_credit_refuses_missing_and_last_credit(catalog):
    conn, ids = catalog
    with pytest.raises(RuntimeError, match="without credits"):
        credits.apply(conn, removal(ids, ("sand", "vocalo")), write=False)
    conn.rollback()
    with pytest.raises(RuntimeError, match="not found"):
        credits.apply(conn, removal(ids, ("sand", "hachi")), write=False)
    conn.rollback()


def test_reading_alias_survives_a_later_title_ko():
    manual = {"reading_only": [{"title_native": "負けないで", "label": "마케나이데"},
                               {"title_native": "謎", "label": "나조"}]}
    songs = {1: {"version": 1, "title_native": "負けないで", "title_ko": "지지 말아요", "external": [("vocadb", "7")]},
             2: {"version": 1, "title_native": "謎", "title_ko": "나조", "external": [("vocadb", "8")]}}
    found = {("vocadb", "7"): [{"qid": "Q7", "ko": "마케나이데"}], ("vocadb", "8"): [{"qid": "Q8", "ko": "나조"}]}
    decisions = wd.plan({"catalog_instance_id": "x", "wikidata": {}, "songs": songs}, found, manual)
    by_song = {d["song_id"]: d for d in decisions["songs"]}
    assert (by_song[1]["title_ko"], by_song[1]["alias_ko"]) == (None, "마케나이데")
    assert (by_song[2]["title_ko"], by_song[2]["alias_ko"]) == (None, None)   # alias equal to the title is not added


def test_review_drops_rows_the_user_never_saw(tmp_path):
    ev = {"qid": "Q1", "via": [], "labels": {"ko": "라벨", "ja": None, "en": None}}
    shown = {"policy": wd.POLICY, "catalog_instance_id": "x", "conflicts": [], "songs": [
        {"song_id": 1, "version": 1, "title_native": "負けないで", "wikidata": None, "title_ko": None,
         "alias_ko": "마케나이데", "evidence": ev}]}
    (tmp_path / "r.md").write_text(wd.render_review(shown, "x.json"), encoding="utf-8")
    later = {**shown, "songs": shown["songs"] + [
        {"song_id": 2, "version": 1, "title_native": "恋愛写真", "wikidata": None, "title_ko": None,
         "alias_ko": "렌아이샤신", "evidence": ev}]}
    result, changes = wd.apply_review(later, wd.read_review(tmp_path / "r.md"))
    assert [s["song_id"] for s in result["songs"]] == [1]
    assert changes == [{"song_id": 2, "field": "alias_ko", "from": "렌아이샤신", "to": None, "reason": "not in review"}]
