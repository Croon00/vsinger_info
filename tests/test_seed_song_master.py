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
              "split_works": [{"provider": "musicbrainz_work", "external_id": W1}],
              "artist_overrides": [{"ref": "A002", "is_virtual": False, "reason": "not a VTuber"}],
              "keys": [{"key_id": k["haikei"], "new_song": {"title_native": "拝啓、はじまりの色", "artist_ids": [a["ヨノ"]]}}]}
    return {"report_name": "candidates-test.json", "report": report, "research": research,
            "research_refs": [{"ref": "A001", "setlist_spellings": ["YOASOBI"]},
                              {"ref": "A002", "setlist_spellings": ["大江千里"]}],
            "review": [], "manual": manual}


def test_plan_joins_one_work_and_follows_catalog_rules(catalog):
    conn, a, s, k = catalog
    decisions = seed.plan(seed.load_state(conn), inputs(a, s, k))
    conn.rollback()
    existing = {e["song_id"]: e for e in decisions["existing_songs"]}
    assert s["nakashima"] not in existing  # split_works exception: the work ID stays with amazarashi
    assert existing[s["amazarashi"]]["external_ids"][0]["external_id"] == W1
    assert existing[s["lemon"]]["external_ids"][0]["external_id"] == "11"
    songs = {(x["title_native"], tuple(sorted(map(str, x["artists"])))): x for x in decisions["new_songs"]}
    rain, = [x for x in decisions["new_songs"] if x["title_native"] == "Rain"]   # one work, one song
    assert rain["artists"] == [{"artist_ref": "A002"}, {"artist_id": a["秦基博"]}]  # work-credited 大江千里 first
    assert rain["external_ids"][0]["external_id"] == W2 and rain["language_code"] == "en"
    assert sorted(rain["keys"]) == sorted([k["rain_oe"], k["rain_hata"]]) and rain["same_work_as_other_artist"] is None
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
    assert q(conn, "SELECT count(*) AS n FROM songs").fetchone()["n"] == 3 + 3
    new_artist = q(conn, "SELECT * FROM artists WHERE slug='yoasobi'").fetchone()
    assert (new_artist["name_ko"], new_artist["show_in_catalog"], new_artist["entity_kind"]) == (None, False, "group")
    assert q(conn, "SELECT alias FROM artist_aliases WHERE artist_id=%s", (new_artist["id"],)).fetchone()["alias"] == "ヨアソビ"
    ext = {(r["provider"], r["external_id"]): r["song_id"] for r in q(conn, "SELECT * FROM song_external_ids")}
    assert ext[("musicbrainz_work", W1)] == s["amazarashi"] and len(ext) == 4
    assert q(conn, "SELECT title_latin FROM songs WHERE id=%s", (s["lemon"],)).fetchone()["title_latin"] is None
    keys = {r["id"]: r for r in q(conn, "SELECT * FROM song_match_keys")}
    assert all(r["status"] == "confirmed" and r["evidence"]["review"] == seed.POLICY for r in keys.values())
    rain = keys[k["rain_hata"]]["song_id"]
    assert rain == keys[k["rain_oe"]]["song_id"]   # one work, one song
    credits = [r["artist_id"] for r in q(conn, "SELECT artist_id FROM song_artists WHERE song_id=%s ORDER BY position", (rain,))]
    assert credits[1] == a["秦基博"] and len(credits) == 2
    receipt = q(conn, "SELECT id, result_summary FROM catalog_imports").fetchone()
    assert receipt["result_summary"]["new_songs"] == 3
    changes = q(conn, "SELECT entity_type, action, count(*) AS n FROM catalog_changes GROUP BY 1,2").fetchall()
    assert {(c["entity_type"], c["action"]): c["n"] for c in changes} == {
        ("artists", "create"): 2, ("songs", "create"): 3, ("songs", "update"): 2, ("song_match_keys", "update"): 5}
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



def credit(name, external_id, role="performer"):
    return {"name": name, "aliases": [], "role": role, "external_id": external_id}


def test_round_two_manual_merge_same_person_and_joint_credit(catalog):
    conn, a, s, k = catalog
    ringo = row(conn, "artists", slug="ringo", name_native="椎名林檎", entity_kind="solo")
    ayaka = row(conn, "artists", slug="ayaka", name_native="絢香", entity_kind="solo")
    extra = {name: row(conn, "song_match_keys", title_key=title, artist_key=artist, sample_raw_title=title,
                       sample_raw_artist=artist, occurrence_count=n)
             for name, title, artist, n in (("dh", "おとなの掟", "doughnuts hole", 5), ("ringo", "おとなの掟", "椎名林檎", 3),
                                             ("melt", "メルト", "ryo(supercell)", 4), ("world", "ワールドイズマイン", "ryo", 2),
                                             ("winding", "winding road", "絢香×コブクロ", 2))}
    conn.commit()
    w3 = "99c9adca-a465-473f-999c-e623c7e399a2"
    data = inputs(a, s, k)
    data["report"]["items"] += [
        item("key", extra["dh"], "おとなの掟", "Doughnuts Hole", 5,
             [candidate("musicbrainz_work", w3, "おとなの掟", composer="椎名林檎", performer="Doughnuts Hole")]),
        item("key", extra["ringo"], "おとなの掟", "椎名林檎", 3,
             [candidate("musicbrainz_work", w3, "おとなの掟", composer="椎名林檎", performer="椎名林檎")], our=[ringo]),
        item("key", extra["melt"], "メルト", "ryo(supercell)", 4, [candidate("vocadb", "1", "メルト", composer="ryo")]),
        item("key", extra["world"], "ワールドイズマイン", "ryo", 2, [candidate("vocadb", "2", "ワールドイズマイン", composer="ryo")]),
        item("key", extra["winding"], "WINDING ROAD", "絢香×コブクロ", 2,
             [candidate("musicbrainz_work", "3f0e3c7a-0000-4000-8000-000000000003", "WINDING ROAD", performer="絢香×コブクロ")])]
    base = {"entity_kind": "group", "is_virtual": False, "aliases": [], "existing_artist_id": None, "confidence": "high",
            "sources": []}
    data["research"] += [{**base, "ref": "B001", "name_native": "Doughnuts Hole", "slug": "doughnuts-hole"},
                         {**base, "ref": "B002", "name_native": "ryo", "slug": "ryo", "entity_kind": "solo"},
                         {**base, "ref": "B003", "name_native": "ryo", "slug": "ryo-2", "entity_kind": "solo"},
                         {**base, "ref": "B004", "name_native": "コブクロ", "name_ko": "코부쿠로", "slug": "kobukuro"},
                         {**base, "ref": "B005", "name_native": "絢香×コブクロ", "slug": "ayaka-kobukuro"}]
    data["research_refs"] += [{"ref": "B001", "setlist_spellings": ["Doughnuts Hole"]},
                              {"ref": "B002", "setlist_spellings": ["ryo(supercell)"]},
                              {"ref": "B003", "setlist_spellings": ["ryo"]},
                              {"ref": "B005", "setlist_spellings": ["絢香×コブクロ"]}]
    data["manual"].update(
        merge_works=[{"provider": "musicbrainz_work", "external_id": w3, "artists_from_keys": [extra["dh"], extra["ringo"]]}],
        artist_overrides=[*data["manual"]["artist_overrides"], {"ref": "B003", "same_as": "B002"}],
        key_artists=[{"key_id": extra["winding"], "artists": [{"artist_id": ayaka}, {"research_ref": "B004"}]}])
    decisions = seed.plan(seed.load_state(conn), data)
    conn.rollback()
    by_title = {}
    for song in decisions["new_songs"]:
        by_title.setdefault(song["title_native"], []).append(song)
    otona, = by_title["おとなの掟"]
    assert otona["artists"] == [{"artist_ref": "B001"}, {"artist_id": ringo}]
    assert otona["external_ids"][0]["external_id"] == w3 and sorted(otona["keys"]) == sorted([extra["dh"], extra["ringo"]])
    assert by_title["メルト"][0]["artists"] == by_title["ワールドイズマイン"][0]["artists"] == [{"artist_ref": "B002"}]
    assert by_title["WINDING ROAD"][0]["artists"] == [{"artist_id": ayaka}, {"artist_ref": "B004"}]
    refs = {x["ref"] for x in decisions["new_artists"]}
    assert {"B001", "B002", "B004"} <= refs and not {"B003", "B005"} & refs


def test_prepare_groups_by_provider_artist_and_skips_held_keys(catalog):
    conn, a, s, k = catalog
    state = seed.load_state(conn)
    conn.rollback()
    arai = {**candidate("vocadb", "7", "春よ、来い"), "artists": [credit("荒井由実", "55", "producer")],
            "matched_artists": ["荒井由実"]}
    free = {**candidate("vocadb", "8", "夜に駆ける"), "artists": [credit("荒井由実", None, "producer")],
            "matched_artists": ["荒井由実"]}
    report = {"items": [
        item("key", k["yoru"], "春よ、来い", "荒井由実", 9, [arai]),
        item("key", k["rain_oe"], "卒業写真", "松任谷由実", 4,
             [{**arai, "artists": [{**credit("松任谷由実", "55", "producer"), "aliases": ["荒井由実"]}], "matched_artists": ["松任谷由実"]}]),
        item("key", k["rain_hata"], "夜に駆ける", "Somebody", 6, [free]),
        item("key", k["lemon2"], "Lemon", "米津玄師", 3, [candidate("vocadb", "11", "Lemon")], status="review"),
        item("key", k["haikei"], "拝啓、はじまりの色", "ヨノ", 2, [candidate("vocadb", "12", "拝啓")], status="review")]}
    files = seed.prepare(state, report, {"hold_keys": [{"key_id": k["haikei"]}]}, prefix="B", chunks=2)
    refs = files["artist-research-refs.json"]
    assert [sorted(r["setlist_spellings"]) for r in refs] == [["松任谷由実", "荒井由実"], ["Somebody"]]
    assert refs[0]["ref"] == "B001" and refs[0]["provider_credits"][0]["artist_external_id"] == "55"
    assert refs[1]["provider_credits"] == []   # a credit without a provider ID joins nothing
    assert [i["key_id"] for i in files["review-input.json"]["items"]] == [k["lemon2"]]
    assert "artist-research-input-2.json" in files and "yono" in files["existing-slugs.json"]


def test_new_songs_found_through_two_providers_become_one_song():
    def song(ref, title, artists, provider, keys):
        return {"ref": ref, "title_native": title, "title_latin": None, "title_ko": None, "language_code": None,
                "artists": artists, "external_ids": [{"provider": provider, "external_id": ref, "url": None}] if provider else [],
                "same_work_as_other_artist": None if provider else ["vocadb", "x"], "basis": "auto", "keys": keys}
    songs = [song("S1", "ninelie", [{"artist_id": 1}], "musicbrainz_work", [1]),
             song("S2", "ninelie", [{"artist_id": 1}, {"artist_id": 95}], "utaitedb", [2, 3]),
             song("S3", "愛のうた", [{"artist_ref": "B1"}], "musicbrainz_work", [4]),
             song("S4", "愛のうた", [{"artist_ref": "B2"}], "musicbrainz_work", [5]),       # another artist: kept apart
             song("S5", "ファンサ", [{"artist_id": 750}], "vocadb", [6]),
             song("S6", "ファンサ", [{"artist_ref": "B3"}], None, [7])]
    plans = [{"key_id": n, "song_ref": s["ref"]} for s in songs for n in s["keys"]]
    merged = seed.merge_new_songs(songs, plans, [{"keys": [6, 7], "artists_from_keys": [6, 7]}])
    by_title = {}
    for s in merged:
        by_title.setdefault(s["title_native"], []).append(s)
    ninelie, = by_title["ninelie"]
    assert ninelie["artists"] == [{"artist_id": 1}, {"artist_id": 95}] and sorted(ninelie["keys"]) == [1, 2, 3]
    assert {e["provider"] for e in ninelie["external_ids"]} == {"musicbrainz_work", "utaitedb"}
    assert len(by_title["愛のうた"]) == 2
    fansa, = by_title["ファンサ"]
    assert fansa["artists"] == [{"artist_id": 750}, {"artist_ref": "B3"}] and fansa["same_work_as_other_artist"] is None
    assert {p["key_id"]: p["song_ref"] for p in plans} == {1: "S1", 2: "S1", 3: "S1", 4: "S3", 5: "S4", 6: "S5", 7: "S5"}