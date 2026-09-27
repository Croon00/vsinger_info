"""Reviewed Korean title candidates, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("title_ko_candidates", ROOT / "scripts/title_ko_candidates.py")
tk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tk)


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def song(id_, title, n, title_ko=None):
    return {"id": id_, "version": 1, "title_native": title, "title_latin": None, "title_ko": title_ko, "language_code": "ja",
            "performances": n, "artists": [{"name": "A", "name_ko": None}], "external_ids": [], "ko_aliases": []}


def test_select_skips_titled_latin_and_wikidata_songs():
    songs = [song(1, "夜に駆ける", 9, "밤을 달리다"), song(2, "Lemon", 8), song(3, "謎", 7), song(4, "負けないで", 6), song(5, "青と夏", 5)]
    picked = tk.select(songs, {3: {"title_ko": "나조"}, 4: {"title_ko": None, "alias_ko": "마케나이데"}}, top=2)
    assert [(p["song_id"], p["reading_in_hangul"]) for p in picked] == [(4, "마케나이데"), (5, None)]


def test_export_prefills_accept_only_for_sourced_high_confidence():
    songs = [song(4, "負けないで", 6), song(5, "青と夏", 5), song(6, "晩餐歌", 4), song(7, "天体観測", 3)]
    inputs = [{"song_id": s["id"], "artists": s["artists"], "performances": s["performances"]} for s in songs]
    research = [
        {"song_id": 4, "title_ko": "지지 말아요", "basis": "korean_usage", "confidence": "high", "sources": ["https://example.test/a"]},
        {"song_id": 5, "title_ko": "푸름과 여름", "basis": "translation", "confidence": "medium", "sources": []},
        {"song_id": 6, "title_ko": "Bansanka", "basis": "translation", "confidence": "low"},            # not Korean
        {"song_id": 7, "title_ko": "천체관측", "basis": "ko_wikipedia", "confidence": "high", "sources": []},  # no source
        {"song_id": 99, "title_ko": "x", "basis": "translation"}]
    out = tk.export(songs, inputs, research)
    by = {i["song_id"]: i for i in out["items"]}
    assert [by[n]["decision"] for n in (4, 5, 6, 7)] == ["accept", "review", "skip", "review"]
    assert by[6]["title_ko"] is None and out["problems"] == [{"song_id": 99, "reason": "unknown or duplicate song in research"}]
    assert out["summary"]["performances_accept"] == 6
    fixed = tk.export(songs, inputs, research[:2], {"overrides": [{"song_id": 5, "title_ko": "파랑과 여름", "reason": "x"}]})
    five = next(i for i in fixed["items"] if i["song_id"] == 5)
    assert (five["title_ko"], five["decision"], five["alternatives"][0]["title_ko"]) == ("파랑과 여름", "review", "푸름과 여름")
    namu = [{"song_id": 5, "namu_title_ko": "푸름과 여름", "where": "content", "evidence": "푸름과 여름(青と夏)",
             "url": "https://namu.wiki/w/x", "same_song": True},
            {"song_id": 6, "namu_title_ko": "만찬가", "where": "document_title", "evidence": "만찬가", "url": "u6", "same_song": True},
            {"song_id": 7, "namu_title_ko": "차가운 상어", "where": "content", "evidence": "다른 곡 이야기", "url": "u7", "same_song": True}]
    by = {i["song_id"]: i for i in tk.export(songs, inputs, research, None, namu)["items"]}
    assert (by[5]["decision"], by[5]["basis"], by[5]["sources"][0]) == ("accept", "korean_usage", "https://namu.wiki/w/x")
    assert (by[6]["title_ko"], by[6]["decision"]) == ("만찬가", "review")          # no research title to agree with
    assert (by[7]["title_ko"], by[7]["decision"], by[7]["confidence"]) == ("차가운 상어", "review", "medium")  # snippet lacks 天体観測
    assert by[7]["alternatives"][0]["title_ko"] == "천체관측"
    reviewed = tk.export(songs, inputs, research, {"user_review": {"approved": "all", "date": "d",
                                                                    "titles": [{"song_id": 6, "title_ko": "만찬의 노래"}]}}, namu)
    by = {i["song_id"]: i for i in reviewed["items"]}
    assert all(i["decision"] == "accept" for i in reviewed["items"])
    assert (by[6]["title_ko"], by[6]["basis"], by[6]["alternatives"][0]["title_ko"]) == ("만찬의 노래", "user_review", "만찬가")


def test_review_file_round_trip():
    decisions = {"items": [
        {"song_id": 1, "title_native": "粉雪", "artists": ["A"], "performances": 9, "title_ko": "가랑눈", "basis": "korean_usage",
         "alternatives": [{"title_ko": "가루눈"}], "note": "namu.wiki x", "namu": "가랑눈", "decision": "review"},
        {"song_id": 2, "title_native": "青と夏", "artists": ["B"], "performances": 5, "title_ko": "푸름과 여름", "basis": "translation",
         "alternatives": [], "note": None, "decision": "accept"},
        {"song_id": 3, "title_native": "Fire◎Flower", "artists": ["C"], "performances": 1, "title_ko": "파이어 플라워",
         "basis": "reading", "alternatives": [], "note": None, "decision": "review"}]}
    text = tk.render_review(decisions, "x.json")
    assert "| ◇ 가랑눈 |" in text and "| ✔ 푸름과 여름 |" in text and "발음 표기" in text
    edited = text.replace("◇ 가랑눈", "가루눈").replace("파이어 플라워", "-")
    path = ROOT / "db-migration" / "_test-review.md"
    try:
        path.write_text(edited, encoding="utf-8")
        titles = tk.read_review(path)
    finally:
        path.unlink(missing_ok=True)
    assert titles == {1: "가루눈", 2: "푸름과 여름", 3: None}
    assert tk.review_edits(decisions, titles) == [{"song_id": 1, "title_ko": "가루눈", "was": "가랑눈"},
                                                  {"song_id": 3, "title_ko": None, "was": "파이어 플라워"}]


def test_apply_writes_only_accepted_titles_once(database):
    apply_schema(database)
    a = row(database, "songs", title_native="負けないで")
    b = row(database, "songs", title_native="青と夏")
    database.commit()
    catalog = q(database, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    database.rollback()
    decisions = {"policy": tk.POLICY, "catalog_instance_id": catalog, "items": [
        {"song_id": a, "version": 1, "title_ko": "지지 말아요", "decision": "accept", "basis": "korean_usage",
         "confidence": "high", "sources": ["https://example.test/a"]},
        {"song_id": b, "version": 1, "title_ko": "푸름과 여름", "decision": "review", "basis": "translation",
         "confidence": "medium", "sources": []}]}
    assert tk.apply(database, decisions, write=False)["accept"] == 1
    database.rollback()
    assert tk.apply(database, decisions, write=True)["status"] == "committed"
    database.commit()
    titles = {r["id"]: r["title_ko"] for r in q(database, "SELECT id, title_ko FROM songs")}
    assert titles == {a: "지지 말아요", b: None}
    assert q(database, "SELECT provenance FROM catalog_changes").fetchone()["provenance"]["basis"] == "korean_usage"
    assert tk.apply(database, decisions, write=True)["status"] == "already_committed"
    database.rollback()
    decisions["items"][1]["decision"] = "maybe"
    with pytest.raises(RuntimeError, match="Invalid decisions"):
        tk.apply(database, decisions, write=False)
    database.rollback()
