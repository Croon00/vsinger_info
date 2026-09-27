"""Korean titles from Wikidata by stored external ID, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import httpx
import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wikidata_title_ko", ROOT / "scripts/wikidata_title_ko.py")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)

W1 = "9e1908fb-d2ad-3749-9564-c45dc4e4b7d6"
W2 = "bdd6d7aa-8846-3934-857e-4ffef1f4f4a2"


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def test_korean_title_rules():
    assert wd.korean_title("나조 (코마츠 미호의 싱글)", "謎") == "나조"
    assert wd.korean_title("OK! (마츠모토 리카의 싱글)", "OK!") is None          # left with the native Latin title
    assert wd.korean_title("Lemon", "Lemon") is None                            # not Hangul
    assert wd.korean_title("장식이 아니야, 눈물은", "飾りじゃないのよ涙は") == "장식이 아니야, 눈물은"
    assert wd.korean_title("사랑 (Love)", "愛") == "사랑 (Love)"                # a real parenthesis stays
    assert wd.korean_title(None, "謎") is None


def state(songs, wikidata=None):
    return {"catalog_instance_id": "x", "wikidata": wikidata or {},
            "songs": {s["id"]: {"version": 1, "title_ko": None, **s} for s in songs}}


def test_plan_needs_one_item_per_song_and_one_song_per_item():
    songs = [{"id": 1, "title_native": "謎", "external": [("vocadb", "5"), ("musicbrainz_work", W1)]},
             {"id": 2, "title_native": "さんぽ", "external": [("musicbrainz_work", W2)]},
             {"id": 3, "title_native": "となりのトトロ", "external": [("vocadb", "9")]},
             {"id": 4, "title_native": "負けないで", "external": [("vocadb", "7"), ("musicbrainz_work", "m4")]},
             {"id": 5, "title_native": "Lemon", "external": [("vocadb", "8")], "title_ko": "레몬"}]
    found = {("vocadb", "5"): [{"qid": "Q1", "ko": "나조 (코마츠 미호의 싱글)"}], ("musicbrainz_work", W1): [{"qid": "Q1", "ko": "나조"}],
             ("musicbrainz_work", W2): [{"qid": "Q9", "ko": "이웃집 토토로"}], ("vocadb", "9"): [{"qid": "Q9", "ko": "이웃집 토토로"}],
             ("vocadb", "7"): [{"qid": "Q4", "ko": "마케나이데"}], ("musicbrainz_work", "m4"): [{"qid": "Q44"}],
             ("vocadb", "8"): [{"qid": "Q5", "ko": "레몬"}]}
    decisions = wd.plan(state(songs), found)
    by_song = {d["song_id"]: d for d in decisions["songs"]}
    assert by_song[1]["title_ko"] == "나조" and by_song[1]["wikidata"] == "Q1"
    assert sorted(by_song[1]["evidence"]["via"]) == [["musicbrainz_work", W1], ["vocadb", "5"]]
    assert by_song[5] == {**by_song[5], "title_ko": None, "wikidata": "Q5"}   # existing title_ko is never replaced
    assert {c["song_id"] for c in decisions["conflicts"]} == {2, 3, 4}        # shared item / two items
    assert decisions["summary"]["title_ko"] == 1


def test_apply_writes_title_and_qid_once(database):
    apply_schema(database)
    song = row(database, "songs", title_native="謎")
    other = row(database, "songs", title_native="Lemon", title_ko="레몬")
    reading = row(database, "songs", title_native="負けないで")
    row(database, "song_external_ids", song_id=song, provider="musicbrainz_work", external_id=W1)
    row(database, "song_external_ids", song_id=reading, provider="vocadb", external_id="7")
    database.commit()
    loaded = wd.load_state(database)
    database.rollback()
    found = {("musicbrainz_work", W1): [{"qid": "Q11632163", "ko": "나조 (코마츠 미호의 싱글)"}],
             ("vocadb", "7"): [{"qid": "Q1045976", "ko": "마케나이데"}]}
    manual = {"reading_only": [{"title_native": "負けないで", "label": "마케나이데"}]}
    decisions = wd.plan(loaded, found, manual)
    assert wd.apply(database, decisions, write=False)["status"] == "would_commit"
    database.rollback()
    result = wd.apply(database, decisions, write=True)
    database.commit()
    assert (result["status"], result["title_ko"], result["alias_ko"], result["wikidata_ids"]) == ("committed", 1, 1, 2)
    assert q(database, "SELECT title_ko FROM songs WHERE id=%s", (song,)).fetchone()["title_ko"] == "나조"
    assert q(database, "SELECT title_ko FROM songs WHERE id=%s", (other,)).fetchone()["title_ko"] == "레몬"
    assert q(database, "SELECT title_ko FROM songs WHERE id=%s", (reading,)).fetchone()["title_ko"] is None
    assert q(database, "SELECT alias, locale, source FROM song_aliases").fetchone() == {
        "alias": "마케나이데", "locale": "ko", "source": "wikidata"}
    assert {r["external_id"] for r in q(database, "SELECT external_id FROM song_external_ids WHERE provider='wikidata'")} == {
        "Q11632163", "Q1045976"}
    change = q(database, "SELECT after_data, provenance FROM catalog_changes WHERE entity_id=%s", (song,)).fetchone()
    assert change["after_data"] == {"title_ko": "나조", "wikidata": "Q11632163"} and change["provenance"]["license"] == "CC0"
    assert wd.apply(database, decisions, write=True)["status"] == "already_committed"
    database.rollback()
    database.execute("UPDATE songs SET title_ko='다른 제목' WHERE id=%s", (song,))
    database.commit()
    stale = wd.plan(loaded, {("musicbrainz_work", W1): [{"qid": "Q2", "ko": "나조"}]})
    with pytest.raises(RuntimeError, match="changed since export"):
        wd.apply(database, stale, write=False)
    database.rollback()


def test_lookup_batches_and_caches(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"results": {"bindings": [
            {"item": {"value": "http://www.wikidata.org/entity/Q7"}, "id": {"value": "7"}, "ko": {"value": "마케나이데"}}]}})

    client = wd.Wikidata(tmp_path / "cache.json", transport=httpx.MockTransport(respond), interval=0)
    assert client.lookup("vocadb", ["7", "8"]) == {"7": [{"qid": "Q7", "ko": "마케나이데"}], "8": []}
    assert "P11100" in calls[0].content.decode() and len(calls) == 1
    again = wd.Wikidata(tmp_path / "cache.json", transport=httpx.MockTransport(respond), interval=0)
    assert again.lookup("vocadb", ["7"]) == {"7": [{"qid": "Q7", "ko": "마케나이데"}]} and len(calls) == 1
    client.close(); again.close()



def test_review_file_round_trip(tmp_path):
    ev = lambda q: {"qid": q, "via": [], "labels": {"ko": "라벨", "ja": "ラベル", "en": None}}
    decisions = {"policy": wd.POLICY, "catalog_instance_id": "x", "conflicts": [], "songs": [
        {"song_id": 1, "version": 1, "title_native": "謎", "wikidata": "Q1", "title_ko": "나조", "alias_ko": None, "evidence": ev("Q1")},
        {"song_id": 2, "version": 1, "title_native": "負けないで", "wikidata": "Q2", "title_ko": None, "alias_ko": "마케나이데",
         "evidence": ev("Q2")},
        {"song_id": 3, "version": 1, "title_native": "愛", "wikidata": "Q3", "title_ko": None, "alias_ko": None, "evidence": ev("Q3")}]}
    text = wd.render_review(decisions, "x.json")
    edited = text.replace("| 1 | 謎 | 나조 |", "| 1 | 謎 | 수수께끼 |").replace("| 2 | 負けないで | 마케나이데 |", "| 2 | 負けないで | - |")
    edited = edited.replace("| 3 | 愛 | ラベル | 라벨 | Q3 |", "| 3 | 愛 | ラベル | 라벨 | - |")
    (tmp_path / "r.md").write_text(edited, encoding="utf-8")
    result, changes = wd.apply_review(decisions, wd.read_review(tmp_path / "r.md"))
    assert [(c["song_id"], c["field"], c["to"]) for c in changes] == [(1, "title_ko", "수수께끼"), (2, "alias_ko", None), (3, "wikidata", None)]
    assert [(s["song_id"], s["title_ko"], s["alias_ko"], s["wikidata"]) for s in result["songs"]] == [
        (1, "수수께끼", None, "Q1"), (2, None, None, "Q2")]