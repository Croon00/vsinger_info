"""Song master seeding on a disposable local PostgreSQL; never reaches Neon."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("seed_song_master", ROOT / "scripts/seed_song_master.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

W1 = "b3919faf-7f88-40a5-aef6-006ef103e275"
W2 = "b86800d4-00e8-4496-899f-5bba0bc1bb41"


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def candidate(provider, external_id, title, *, composer=None, performer=None, latin=None, language="jpn"):
    return {"provider": provider, "external_id": external_id, "url": f"https://example.test/{external_id}",
            "title": title, "names": [{"value": title, "language": "work"}], "language": language,
            "artists": [{"name": composer, "aliases": [], "role": "composer", "external_id": None}] if composer else [],
            "performers": [{"name": performer, "aliases": [], "role": "performer", "external_id": None}] if performer else [],
            "title_latin": latin, "title_ko": None, "title_exact": True, "artist_exact": True}


def item(kind, ref, title, artist, count, cands, *, status="auto", our=()):
    return {"kind": kind, "ref": ref, "title": title, "artist": artist, "title_key": title.casefold(), "count": count,
            "our_artist_ids": list(our), "status": status, "providers": [], "errors": [], "candidates": cands}


@pytest.fixture
def catalog(database):
    apply_schema(database)
    a = {name: row(database, "artists", slug=slug, name_native=name, entity_kind="solo")
         for slug, name in (("nakashima", "中島美嘉"), ("amazarashi", "amazarashi"), ("yono", "ヨノ"),
                            ("yonezu", "米津玄師"), ("hata", "秦基博"))}
    s = {"nakashima": row(database, "songs", title_native="僕が死のうと思ったのは"),
         "amazarashi": row(database, "songs", title_native="僕が死のうと思ったのは"),
         "lemon": row(database, "songs", title_native="Lemon")}
    for song, artist in (("nakashima", "中島美嘉"), ("amazarashi", "amazarashi"), ("lemon", "米津玄師")):
        row(database, "song_artists", song_id=s[song], artist_id=a[artist])
    k = {}
    for name, title, artist, count in (("lemon2", "lemon ", "米津玄師", 3), ("yoru", "夜に駆ける", "yoasobi", 9),
                                       ("rain_oe", "rain", "大江千里", 4), ("rain_hata", "rain", "秦基博", 6),
                                       ("haikei", "拝啓、はじまりの色", "ヨノ", 2)):
        k[name] = row(database, "song_match_keys", title_key=title.strip(), artist_key=artist.casefold(),
                      sample_raw_title=title.strip(), sample_raw_artist=artist, occurrence_count=count)
    database.commit()
    return database, a, s, k


def inputs(a, s, k):
    report = {"items": [
        item("song", s["nakashima"], "僕が死のうと思ったのは", "中島美嘉", 5,
             [candidate("musicbrainz_work", W1, "僕が死のうと思ったのは", composer="秋田ひろむ", performer="中島美嘉")]),
        item("song", s["amazarashi"], "僕が死のうと思ったのは", "amazarashi", 2,
             [candidate("musicbrainz_work", W1, "僕が死のうと思ったのは", composer="秋田ひろむ", performer="amazarashi")]),
        item("song", s["lemon"], "Lemon", "米津玄師", 8, [candidate("vocadb", "11", "Lemon", composer="米津玄師", latin="Lemon")]),
        item("key", k["yoru"], "夜に駆ける", "YOASOBI", 9,
             [candidate("musicbrainz_work", "0f6e2d1c-5b4a-4c3d-8e2f-1a2b3c4d5e6f", "夜に駆ける", composer="Ayase",
                        performer="YOASOBI", latin="Yoru ni Kakeru")]),
        item("key", k["rain_oe"], "Rain", "大江千里", 4,
             [candidate("musicbrainz_work", W2, "Rain", composer="大江千里", performer="大江千里", language="eng")]),
        item("key", k["rain_hata"], "Rain", "秦基博", 6,
             [candidate("musicbrainz_work", W2, "Rain", composer="大江千里", performer="秦基博", language="eng")],
             our=[a["秦基博"]]),
        item("key", k["lemon2"], "Lemon", "米津玄師", 3, [candidate("vocadb", "11", "Lemon", composer="米津玄師")],
             our=[a["米津玄師"]]),
    ]}
    research = [{"ref": "A001", "name_native": "YOASOBI", "name_ko": "요아소비", "name_latin": "YOASOBI",
                 "entity_kind": "group", "is_virtual": False, "slug": "yoasobi", "aliases": ["ヨアソビ"],
                 "existing_artist_id": None, "confidence": "high", "sources": ["https://example.test/y"]},
                {"ref": "A002", "name_native": "大江千里", "name_ko": "오에 센리", "name_latin": "Ōe Senri",
                 "entity_kind": "solo", "is_virtual": True, "slug": "senri-oe", "aliases": [],
                 "existing_artist_id": None, "confidence": "medium", "sources": []}]
    manual = {"existing_song_external": [
                  {"song_id": s["amazarashi"], "provider": "musicbrainz_work", "external_id": W1},
                  {"song_id": s["nakashima"], "provider": None, "external_id": None}],
              "artist_overrides": [{"ref": "A002", "is_virtual": False, "reason": "not a VTuber"}],
              "keys": [{"key_id": k["haikei"], "new_song": {"title_native": "拝啓、はじまりの色", "artist_ids": [a["ヨノ"]]}}]}
    return {"report_name": "candidates-test.json", "report": report, "research": research,
            "research_refs": [{"ref": "A001", "setlist_spellings": ["YOASOBI"]},
                              {"ref": "A002", "setlist_spellings": ["大江千里"]}],
            "review": [], "manual": manual}


def test_plan_keeps_versions_apart_and_follows_catalog_rules(catalog):
    conn, a, s, k = catalog
    decisions = seed.plan(seed.load_state(conn), inputs(a, s, k))
    conn.rollback()
    existing = {e["song_id"]: e for e in decisions["existing_songs"]}
    assert s["nakashima"] not in existing  # the shared work stays with amazarashi (user decision)
    assert existing[s["amazarashi"]]["external_ids"][0]["external_id"] == W1
    assert existing[s["lemon"]]["external_ids"][0]["external_id"] == "11"
    songs = {(x["title_native"], tuple(sorted(map(str, x["artists"])))): x for x in decisions["new_songs"]}
    rain = [x for x in decisions["new_songs"] if x["title_native"] == "Rain"]
    assert len(rain) == 2
    owner = next(x for x in rain if x["external_ids"])
    other = next(x for x in rain if not x["external_ids"])
    assert owner["artists"] == [{"artist_ref": "A002"}] and owner["language_code"] == "en"
    assert other["artists"] == [{"artist_id": a["秦基博"]}] and other["same_work_as_other_artist"] == ["musicbrainz_work", W2]
    yoru = next(x for x in decisions["new_songs"] if x["title_native"] == "夜に駆ける")
    assert (yoru["title_latin"], yoru["language_code"]) == ("Yoru ni Kakeru", "ja")
    haikei = next(x for x in decisions["new_songs"] if x["title_native"] == "拝啓、はじまりの色")
    assert haikei["artists"] == [{"artist_id": a["ヨノ"]}] and haikei["external_ids"] == [] and haikei["basis"] == "user"
    artists = {x["ref"]: x for x in decisions["new_artists"]}
    assert artists["A001"]["name_ko"] is None  # Latin native name: no Korean name
    assert (artists["A002"]["name_latin"], artists["A002"]["is_virtual"]) == ("Oe Senri", False)
    assert all(x["show_in_catalog"] is False for x in artists.values())
    keys = {x["key_id"]: x for x in decisions["keys"]}
    assert keys[k["lemon2"]]["song_id"] == s["lemon"] and keys[k["yoru"]]["decided_by"] == "musicbrainz"
    assert keys[k["haikei"]]["decided_by"] == "manual" and len(keys) == 5 and songs


def test_apply_writes_everything_once_with_audit(catalog):
    conn, a, s, k = catalog
    decisions = seed.plan(seed.load_state(conn), inputs(a, s, k))
    dry = seed.apply(conn, decisions, write=False)
    conn.rollback()
    assert dry["status"] == "would_commit"
    assert q(conn, "SELECT count(*) AS n FROM songs").fetchone()["n"] == 3
    result = seed.apply(conn, decisions, write=True)
    conn.commit()
    assert result["status"] == "committed"
    assert q(conn, "SELECT count(*) AS n FROM songs").fetchone()["n"] == 3 + 4
    new_artist = q(conn, "SELECT * FROM artists WHERE slug='yoasobi'").fetchone()
    assert (new_artist["name_ko"], new_artist["show_in_catalog"], new_artist["entity_kind"]) == (None, False, "group")
    assert q(conn, "SELECT alias FROM artist_aliases WHERE artist_id=%s", (new_artist["id"],)).fetchone()["alias"] == "ヨアソビ"
    ext = {(r["provider"], r["external_id"]): r["song_id"] for r in q(conn, "SELECT * FROM song_external_ids")}
    assert ext[("musicbrainz_work", W1)] == s["amazarashi"] and len(ext) == 4
    assert q(conn, "SELECT title_latin FROM songs WHERE id=%s", (s["lemon"],)).fetchone()["title_latin"] is None
    keys = {r["id"]: r for r in q(conn, "SELECT * FROM song_match_keys")}
    assert all(r["status"] == "confirmed" and r["evidence"]["review"] == seed.POLICY for r in keys.values())
    rain_hata = keys[k["rain_hata"]]["song_id"]
    assert q(conn, "SELECT artist_id FROM song_artists WHERE song_id=%s", (rain_hata,)).fetchone()["artist_id"] == a["秦基博"]
    assert rain_hata != keys[k["rain_oe"]]["song_id"]
    receipt = q(conn, "SELECT id, result_summary FROM catalog_imports").fetchone()
    assert receipt["result_summary"]["new_songs"] == 4
    changes = q(conn, "SELECT entity_type, action, count(*) AS n FROM catalog_changes GROUP BY 1,2").fetchall()
    assert {(c["entity_type"], c["action"]): c["n"] for c in changes} == {
        ("artists", "create"): 2, ("songs", "create"): 4, ("songs", "update"): 2, ("song_match_keys", "update"): 5}
    assert seed.apply(conn, decisions, write=True)["status"] == "already_committed"
    conn.rollback()


def test_stale_rows_abort_without_writing(catalog):
    conn, a, s, k = catalog
    decisions = seed.plan(seed.load_state(conn), inputs(a, s, k))
    conn.rollback()
    conn.execute("UPDATE song_match_keys SET occurrence_count=99 WHERE id=%s", (k["yoru"],))
    conn.commit()
    with pytest.raises(RuntimeError, match="changed since export"):
        seed.apply(conn, decisions, write=True)
    conn.rollback()
    assert q(conn, "SELECT count(*) AS n FROM artists").fetchone()["n"] == 5
    assert q(conn, "SELECT count(*) AS n FROM song_external_ids").fetchone()["n"] == 0


def test_invalid_research_is_rejected(catalog):
    conn, a, s, k = catalog
    data = inputs(a, s, k)
    data["research"][0]["slug"] = "nakashima"  # collides with an existing artist
    with pytest.raises(ValueError, match="slug"):
        seed.plan(seed.load_state(conn), data)
    data["research"][0].update(slug="yoasobi", entity_kind="unit")
    with pytest.raises(ValueError, match="entity_kind"):
        seed.plan(seed.load_state(conn), data)
    conn.rollback()
