"""Recordings -> songs through ISRC / MusicBrainz work, on a disposable local PostgreSQL.

No MusicBrainz request is made: the lookups are passed to ``plan`` directly, and the
lookup cache is exercised with a fake transport.
"""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from psycopg.rows import dict_row

from app.integrations.song_catalogs import MusicBrainzClient
from test_catalog_migration import local_server, database, apply as apply_schema, row, artist  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("link_recordings_to_songs", ROOT / "scripts/link_recordings_to_songs.py")
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

W_KNOWN = "11111111-1111-1111-1111-111111111111"
W_NEW = "22222222-2222-2222-2222-222222222222"
W_ATTACH = "33333333-3333-3333-3333-333333333333"
W_COVER = "44444444-4444-4444-4444-444444444444"
W_SPLIT = "55555555-5555-5555-5555-555555555555"


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def test_base_title_strips_version_tails_only():
    assert lr.base_title("CH4NGE - Live") == "CH4NGE"
    assert lr.base_title('Opening (Live at Nippon Budokan "Ray") - Instrumental') == "Opening"
    assert lr.base_title("残響散歌 -long intro ver.-") == "残響散歌"
    assert lr.base_title("ラストリゾート (feat. 花譜)") == "ラストリゾート"
    assert lr.base_title("夜に駆ける - From THE FIRST TAKE") == "夜に駆ける"
    assert lr.base_title("HELLO ～Paradise Kiss～") == "HELLO ～Paradise Kiss～"   # no version word
    assert lr.base_title("A - B") == "A - B"
    assert lr.base_title("Intro") == "Intro"                                     # never empties a title
    assert lr.base_title("アイラ at I SCREAM LIVE3 - Cover") == "アイラ"
    assert lr.title_forms("G4L - Happy Merry Xmath - Cover") == {"g4lhappymerryxmath", "g4l"}
    assert lr.tight("命に嫌われている。") == lr.tight("命に嫌われている") and lr.tight("#") == "#"
    assert lr.is_cover("Calc. - Cover Live") and not lr.is_cover("Discovery")


def recording(conn, title, isrc, *artist_ids):
    rec = row(conn, "recordings", title_native=title)
    row(conn, "recording_external_ids", recording_id=rec, platform="isrc", external_id=isrc)
    for n, a in enumerate(artist_ids):
        row(conn, "recording_artists", recording_id=rec, artist_id=a, role="primary", position=n)
    return rec


def song(conn, title, *artist_ids, work=None):
    s = row(conn, "songs", title_native=title)
    for n, a in enumerate(artist_ids):
        row(conn, "song_artists", song_id=s, artist_id=a, position=n)
    if work:
        row(conn, "song_external_ids", song_id=s, provider="musicbrainz_work", external_id=work)
    return s


def work(work_id, title, *writers, language="jpn"):
    return {"id": work_id, "title": title, "language": language, "names": [title],
            "writers": [{"name": w, "role": "composer"} for w in writers]}


def build(conn):
    apply_schema(conn)
    v = artist(conn, "vsinger", show_in_catalog=True)
    conn.execute("UPDATE artists SET name_native='花譜' WHERE id=%s", (v,))
    other = artist(conn, "other")
    conn.execute("UPDATE artists SET name_native='ヨルシカ' WHERE id=%s", (other,))
    writer = artist(conn, "writer")
    conn.execute("UPDATE artists SET name_native='カンザキイオリ' WHERE id=%s", (writer,))
    hidden = artist(conn, "hidden")
    conn.execute("UPDATE artists SET name_native='LiSA' WHERE id=%s", (hidden,))
    ids = {"v": v, "other": other, "writer": writer, "hidden": hidden}
    ids["s_known"] = song(conn, "不可解", v, work=W_KNOWN)
    ids["s_attach"] = song(conn, "未確認少女進行形", v)
    ids["s_writer"] = song(conn, "命に嫌われている。", writer)
    ids["s_cover"] = song(conn, "ただ君に晴れ", other)
    ids["s_split"] = song(conn, "僕が死のうと思ったのは", other, work=W_SPLIT)
    ids["s_hidden"] = song(conn, "紅蓮華", hidden)
    ids["r_known"] = recording(conn, "不可解 - Live", "JPA000000001", v)
    ids["r_attach"] = recording(conn, "未確認少女進行形", "JPA000000002", v)
    ids["r_attach_live"] = recording(conn, "未確認少女進行形 (Live)", "JPA000000003", v)
    ids["r_writer"] = recording(conn, "命に嫌われている。", "JPA000000004", v)
    ids["r_cover"] = recording(conn, "ただ君に晴れ", "JPA000000005", v)
    ids["r_split"] = recording(conn, "僕が死のうと思ったのは", "JPA000000006", v)
    ids["r_new"] = recording(conn, "祈りの唄", "JPA000000007", v)
    ids["r_new_inst"] = recording(conn, "祈りの唄 - Instrumental", "JPA000000008", v)
    ids["r_new_plain"] = recording(conn, "マイディア", "JPA000000009", v)
    ids["r_other_title"] = recording(conn, "ただ君に晴れ", "JPA000000010", other)   # other's own recording
    ids["r_hidden"] = recording(conn, "紅蓮華 -TV ver.-", "JPA000000011", hidden)
    ids["r_hidden_new"] = recording(conn, "炎", "JPA000000012", hidden)
    ids["r_uncredited"] = recording(conn, "不可解 (Instrumental)", "JPA000000013")
    ids["s_matryoshka"] = song(conn, "マトリョシカ", other)
    ids["r_cover_marked"] = recording(conn, "マトリョシカ - Cover Live", "JPA000000014", v)
    ids["r_cover_new"] = recording(conn, "アイラ at I SCREAM LIVE3 - Cover", "JPA000000015", v)
    ids["r_wrong_work"] = recording(conn, "風 - feat. 理芽", "JPA000000016", v)
    conn.commit()
    found = {
        ids["r_known"]: {"mb_recordings": ["m1"], "works": [work(W_KNOWN, "不可解")]},
        ids["r_attach"]: {"mb_recordings": ["m2"], "works": [work(W_ATTACH, "未確認少女進行形")]},
        ids["r_attach_live"]: {"mb_recordings": ["m3"], "works": [work(W_ATTACH, "未確認少女進行形")]},
        ids["r_writer"]: {"mb_recordings": ["m4"], "works": [work("66666666-6666-6666-6666-666666666666",
                                                                  "命に嫌われている", "カンザキイオリ")]},
        ids["r_cover"]: {"mb_recordings": ["m5"], "works": [work(W_COVER, "ただ君に晴れ", "n-buna")]},
        ids["r_split"]: {"mb_recordings": ["m6"], "works": [work(W_SPLIT, "僕が死のうと思ったのは")]},
        ids["r_new"]: {"mb_recordings": ["m7"], "works": [work(W_NEW, "祈りの唄")]},
        ids["r_new_inst"]: {"mb_recordings": ["m8"], "works": [work(W_NEW, "祈りの唄")]},
        ids["r_uncredited"]: {"mb_recordings": ["m9"], "works": [work(W_KNOWN, "不可解")]},
        ids["r_cover_new"]: {"mb_recordings": ["m10"], "works": [work("77777777-7777-7777-7777-777777777777", "アイラ", "n-buna")]},
        ids["r_wrong_work"]: {"mb_recordings": ["m11"], "works": [work("88888888-8888-8888-8888-888888888888", "花")]},
    }
    return ids, found


def test_plan_rules(database):
    ids, found = build(database)
    state = lr.load_state(database)
    database.rollback()
    decisions = lr.plan(state, found, {W_SPLIT})
    links = {link["recording_id"]: link for link in decisions["links"]}
    assert (links[ids["r_known"]]["song_id"], links[ids["r_known"]]["basis"]) == (ids["s_known"], "mb_work")
    assert links[ids["r_uncredited"]]["song_id"] == ids["s_known"]            # stored work links even without credit
    assert (links[ids["r_attach"]]["basis"], links[ids["r_attach"]]["attach_work"]) == ("title_artist", W_ATTACH)
    assert (links[ids["r_attach_live"]]["song_id"], links[ids["r_attach_live"]]["attach_work"]) == (ids["s_attach"], W_ATTACH)
    assert (links[ids["r_writer"]]["song_id"], links[ids["r_writer"]]["basis"]) == (ids["s_writer"], "title_writer")
    assert links[ids["r_other_title"]]["song_id"] == ids["s_cover"]            # the artist's own song
    assert links[ids["r_hidden"]]["song_id"] == ids["s_hidden"]                # hidden artist: existing song only
    assert (links[ids["r_cover_marked"]]["song_id"], links[ids["r_cover_marked"]]["basis"]) == (
        ids["s_matryoshka"], "cover_title")
    review = {r["recording_id"]: r["reason"] for r in decisions["review"]}
    assert review == {ids["r_cover"]: "title_only", ids["r_split"]: "split_work", ids["r_cover_new"]: "cover_unknown"}
    new = {s["title_native"]: s for s in decisions["new_songs"]}
    assert set(new) == {"祈りの唄", "マイディア", "風"}
    assert new["風"]["external_ids"] == []                                     # work "花" does not match the title
    assert [r["recording_id"] for r in new["祈りの唄"]["recordings"]] == [ids["r_new"], ids["r_new_inst"]]
    assert new["祈りの唄"]["external_ids"] == [{"provider": "musicbrainz_work", "external_id": W_NEW}]
    assert new["祈りの唄"]["language_code"] == "ja" and new["マイディア"]["language_code"] is None
    assert new["マイディア"]["artist_ids"] == [ids["v"]]
    assert {s["reason"] for s in decisions["skipped"]} == {"hidden_artist"}   # 炎 by the hidden artist


def test_review_and_apply(database, tmp_path):
    ids, found = build(database)
    state = lr.load_state(database)
    database.rollback()
    decisions = lr.plan(state, found, {W_SPLIT})
    for link in decisions["links"]:
        link["song"] = {"title": "x", "artists": []}
    review = tmp_path / "review.md"
    text = lr.render_review(decisions, "decisions.json")
    new_ref = next(s["ref"] for s in decisions["new_songs"] if s["title_native"] == "マイディア")
    # The user: links the cover, renames a new song, drops the hidden-artist link.
    text = text.replace(f"| {ids['r_cover']} | ただ君に晴れ | 花譜 | - |", f"| {ids['r_cover']} | ただ君に晴れ | 花譜 | song:{ids['s_cover']} |")
    text = text.replace(f"| {new_ref} | マイディア |", f"| {new_ref} | マイ・ディア |")
    text = text.replace(f"| {ids['r_hidden']} | 紅蓮華 -TV ver.- | LiSA | song:{ids['s_hidden']} |",
                        f"| {ids['r_hidden']} | 紅蓮華 -TV ver.- | LiSA | - |")
    review.write_text(text, encoding="utf-8")
    reviewed, changes = lr.apply_review(decisions, lr.read_review(review), set(state["songs"]))
    assert {c.get("recording_id") or c.get("ref") for c in changes} == {ids["r_cover"], new_ref, ids["r_hidden"]}
    assert lr.apply(database, reviewed, write=False)["status"] == "would_commit"
    database.rollback()
    result = lr.apply(database, reviewed, write=True)
    database.commit()
    assert (result["status"], result["new_songs"], result["attach_works"]) == ("committed", 3, 2)
    linked = {r["id"]: r["song_id"] for r in q(database, "SELECT id, song_id FROM recordings")}
    assert linked[ids["r_cover"]] == ids["s_cover"] and linked[ids["r_hidden"]] is None
    assert linked[ids["r_split"]] is None and linked[ids["r_hidden_new"]] is None and linked[ids["r_cover_new"]] is None
    assert linked[ids["r_new"]] == linked[ids["r_new_inst"]] is not None
    renamed = q(database, "SELECT s.id, s.language_code FROM songs s WHERE title_native='マイ・ディア'").fetchone()
    assert linked[ids["r_new_plain"]] == renamed["id"]
    assert q(database, "SELECT artist_id FROM song_artists WHERE song_id=%s", (renamed["id"],)).fetchone()["artist_id"] == ids["v"]
    works = {r["external_id"]: r["song_id"] for r in q(database, "SELECT song_id, external_id FROM song_external_ids")}
    assert works[W_ATTACH] == ids["s_attach"] and works[W_NEW] == linked[ids["r_new"]]
    kinds = q(database, "SELECT entity_type, action, count(*) n FROM catalog_changes GROUP BY 1,2 ORDER BY 1,2").fetchall()
    assert {(k["entity_type"], k["action"]): k["n"] for k in kinds} == {
        ("recordings", "update"): 12, ("songs", "create"): 3, ("songs", "update"): 2}
    assert lr.apply(database, reviewed, write=True)["status"] == "already_committed"
    database.rollback()
    # A recording changed after export makes a fresh plan refuse.
    decisions2 = lr.plan(lr.load_state(database), found, {W_SPLIT})
    database.rollback()
    database.execute("UPDATE recordings SET title_ko='x' WHERE id=%s", (ids["r_split"],))
    database.commit()
    decisions2["links"].append({"recording_id": ids["r_split"], "version": 1, "song_id": ids["s_split"],
                                "attach_work": None, "basis": "manual", "isrc": None, "mb_recordings": [], "works": []})
    with pytest.raises(RuntimeError, match="changed since export"):
        lr.apply(database, decisions2, write=False)
    database.rollback()


def test_lookups_batch_and_cache(tmp_path):
    calls = []

    def handler(request):
        query = request.url.params["query"]
        calls.append((request.url.path, query))
        if request.url.path == "/ws/2/recording":
            return httpx.Response(200, json={"count": 1, "recordings": [
                {"id": "aaaaaaaa-0000-0000-0000-000000000001", "title": "祈りの唄", "isrcs": ["JPA000000007"],
                 "artist-credit": [{"name": "花譜", "artist": {"id": "x", "name": "花譜"}}]}]})
        return httpx.Response(200, json={"count": 1, "works": [
            {"id": W_NEW, "title": "祈りの唄", "language": "jpn",
             "relations": [{"type": "performance", "recording": {"id": "aaaaaaaa-0000-0000-0000-000000000001"}},
                           {"type": "composer", "artist": {"id": "y", "name": "カンザキイオリ"}}]}]})

    client = MusicBrainzClient(transport=httpx.MockTransport(handler), interval=0, sleep=lambda s: None)
    lookups = lr.Lookups(tmp_path / "mb.json", client)
    state = {"recordings": {1: {"isrc": "JPA000000007"}, 2: {"isrc": "JPA000000099"}, 3: {"isrc": None}}}
    found = lr.lookup_all(state, lookups)
    assert found[1]["works"][0]["id"] == W_NEW and found[1]["works"][0]["writers"][0]["name"] == "カンザキイオリ"
    assert found[2] == {"mb_recordings": [], "works": []} and found[3] == {"mb_recordings": [], "works": []}
    assert [c[0] for c in calls] == ["/ws/2/recording", "/ws/2/work"]
    assert "isrc:JPA000000007 OR isrc:JPA000000099" == calls[0][1]
    lookups.close()
    cached = lr.Lookups(tmp_path / "mb.json", None)                    # no client: must not need one
    assert lr.lookup_all(state, cached)[1]["works"][0]["id"] == W_NEW
    assert json.loads((tmp_path / "mb.json").read_text(encoding="utf-8"))["isrc"]["JPA000000099"] == []


def test_cover_lookup_marks_the_whole_group(tmp_path):
    rid = "aaaaaaaa-0000-0000-0000-000000000002"
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": rid, "relations": [
            {"type": "performance", "attributes": ["cover", "live"], "work": {"id": W_NEW}}]})

    lookups = lr.Lookups(tmp_path / "mb.json",
                         MusicBrainzClient(transport=httpx.MockTransport(handler), interval=0, sleep=lambda s: None))
    decisions = {"new_songs": [
        {"external_ids": [{"provider": "musicbrainz_work", "external_id": W_NEW}],
         "recordings": [{"recording_id": 2, "title": "ココロ - Live"}, {"recording_id": 1, "title": "ココロ"}]},
        {"external_ids": [], "recordings": [{"recording_id": 3, "title": "オリジナル"}]}]}
    found = {1: {"mb_recordings": [rid]}, 2: {"mb_recordings": ["other"]}, 3: {"mb_recordings": []}}
    assert lr.cover_lookups(decisions, found, lookups) == {1: True, 2: True}
    assert calls == [f"/ws/2/recording/{rid}"]                               # plain title asked, once
    assert lr.cover_lookups(decisions, found, lookups) == {1: True, 2: True} and len(calls) == 1   # cached
    lookups.close()


def test_mc_tracks_and_mb_covers_make_no_song(database):
    ids, found = build(database)
    mc = recording(database, "MC1 at I SCREAM LIVE2", "JPA000000017", ids["v"])
    database.commit()
    state = lr.load_state(database)
    database.rollback()
    decisions = lr.plan(state, found, {W_SPLIT}, {ids["r_new_plain"]: True})
    assert {"recording_id": mc, "reason": "not_song"} in decisions["skipped"]
    assert "マイディア" not in {s["title_native"] for s in decisions["new_songs"]}
    assert {r["recording_id"]: r["reason"] for r in decisions["review"]}[ids["r_new_plain"]] == "cover_unknown"


def test_live_version_by_another_singer_joins_the_work_song(database):
    ids, found = build(database)
    ciel = artist(database, "ciel", show_in_catalog=True)
    live = recording(database, "祈りの唄 - Live", "JPA000000018", ciel)
    database.commit()
    state = lr.load_state(database)
    database.rollback()
    new = {s["title_native"]: s for s in lr.plan(state, found, {W_SPLIT})["new_songs"]}
    song = new["祈りの唄"]
    assert live in [r["recording_id"] for r in song["recordings"]]
    assert song["artist_ids"] == [ids["v"]] and "has_cover" in song["flags"]     # the live singer is not credited
