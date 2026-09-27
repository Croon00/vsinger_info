"""Reviewed Spotify artist account registration, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("spotify_account_candidates", ROOT / "scripts/spotify_account_candidates.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

A = "A" * 22
B = "B" * 22
C = "C" * 22


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def cand(sid, name, overlap=(), wikidata=(), followers=1):
    return {"spotify_id": sid, "name": name, "overlap": list(overlap), "wikidata": list(wikidata),
            "followers": followers, "albums": [], "top_tracks": []}


def research_row(artist_id, name, candidates):
    return {"artist_id": artist_id, "version": 1, "name_native": name, "variants": [name], "candidates": candidates}


def test_title_overlap_uses_songs_and_own_video_titles():
    hits = sp.title_overlap(["献華", "AI", "ロストメモリー (feat. X)", "Other"], ["ロストメモリー"],
                            ["【MV】献華 / 羽緒", "雑談"])
    assert hits == ["献華", "ロストメモリー (feat. X)"]   # "AI" is too short to count


def test_decide_needs_id_or_content_evidence():
    # Wikidata on a name-exact profile wins even when another same-name profile has a weak hit.
    d = sp.decide(research_row(1, "HACHI", [cand(A, "HACHI", ["Twilight Line"], ["Q1"]), cand(B, "Hachi", ["Rainy proof"])]))
    assert (d["decision"], d["basis"], d["pick"]["spotify_id"]) == ("accept", "wikidata", A)
    # Wikidata pointing at a member profile ("ryo (supercell)") does not decide the group.
    d = sp.decide(research_row(2, "supercell", [cand(A, "supercell", ["The Bravery"]), cand(B, "ryo (supercell)", [], ["Q2"])]))
    assert (d["decision"], d["pick"]["spotify_id"]) == ("review", A)
    d = sp.decide(research_row(3, "ReoNa", [cand(A, "ReoNa", ["ANIMA"])]))
    assert (d["decision"], d["basis"]) == ("accept", "title_overlap")
    d = sp.decide(research_row(4, "NERO", [cand(A, "Nero", followers=5), cand(B, "NERO", followers=9)]))
    assert (d["decision"], d["basis"], d["pick"]["spotify_id"]) == ("review", "name_only", B)
    assert sp.decide(research_row(5, "カスカ", []))["decision"] == "skip"


def test_export_web_manual_and_review_round_trip():
    research = [research_row(1, "ReoNa", [cand(A, "ReoNa", ["ANIMA"])]),
                research_row(2, "NERO", [cand(B, "NERO")]),
                research_row(3, "BAMBI", [cand(C, "bambi")]),
                research_row(4, "CIEL", [cand(C, "CIEL")])]
    web = [{"artist_id": 2, "spotify_id": "D" * 22, "spotify_name": "KMNZ NERO", "confidence": "high", "sources": ["s"]},
           {"artist_id": 3, "spotify_id": None, "confidence": "high", "note": "unrelated rapper"},
           {"artist_id": 4, "spotify_id": C, "spotify_name": "CIEL", "confidence": "medium"},
           {"artist_id": 1, "spotify_id": B, "confidence": "high"}]   # automatic accept is not overridden
    out = sp.export(research, web, {})
    by = {i["artist_id"]: i for i in out["items"]}
    assert [(by[n]["decision"], by[n]["spotify_id"]) for n in (1, 2, 3, 4)] == [
        ("accept", A), ("accept", "D" * 22), ("skip", None), ("review", C)]
    text = sp.render_review(out)
    path = ROOT / "db-migration" / "_test-spotify-review.md"
    try:
        path.write_text(text.replace(f"| {A} |", "| - |", 1), encoding="utf-8")
        ids = sp.read_review(path)
    finally:
        path.unlink(missing_ok=True)
    assert ids == {1: None, 2: "D" * 22, 3: None, 4: C}
    assert sp.review_edits(out, ids) == [{"artist_id": 1, "spotify_id": None, "was": A}]
    manual = {"accounts": [{"artist_id": 1, "spotify_id": None, "decision": "skip", "basis": "user_review"}],
              "user_review": {"approved": "all", "listed": [1, 2, 3, 4]}}
    by = {i["artist_id"]: i for i in sp.export(research, web, manual)["items"]}
    assert [by[n]["decision"] for n in (1, 2, 3, 4)] == ["skip", "accept", "skip", "accept"]
    with pytest.raises(RuntimeError, match="22-character"):
        sp.review_edits(out, {2: "not-an-id"})


def test_apply_creates_or_links_accounts_once(database):
    apply_schema(database)
    a = row(database, "artists", slug="reona", name_native="ReoNa", entity_kind="solo", show_in_catalog=True)
    b = row(database, "artists", slug="ciel", name_native="CIEL", entity_kind="solo", show_in_catalog=True)
    shared = row(database, "external_accounts", platform="spotify", platform_id=C,
                 url=f"https://open.spotify.com/artist/{C}", collection_enabled=False)
    yt = row(database, "external_accounts", platform="youtube", platform_id="UC" + "x" * 22, url="https://www.youtube.com/@r")
    row(database, "artist_external_accounts", artist_id=a, account_id=yt, relationship="owner", position=0)
    database.commit()
    catalog = q(database, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    versions = {r["id"]: r["version"] for r in q(database, "SELECT id, version FROM artists")}
    database.rollback()
    item = {"relationship": "owner", "basis": "wikidata", "evidence": {}, "spotify_name": None}
    decisions = {"policy": sp.POLICY, "catalog_instance_id": catalog, "items": [
        {**item, "artist_id": a, "version": versions[a], "spotify_id": A, "decision": "accept"},
        {**item, "artist_id": b, "version": versions[b], "spotify_id": C, "decision": "accept"}]}
    preview = sp.apply(database, decisions, write=False)
    assert (preview["accounts_created"], preview["existing_accounts_linked"]) == (1, 1)
    database.rollback()
    assert sp.apply(database, decisions, write=True)["status"] == "committed"
    database.commit()
    links = q(database, """SELECT ae.artist_id, e.platform_id, e.collection_enabled, ae.is_primary, ae.position
        FROM artist_external_accounts ae JOIN external_accounts e ON e.id=ae.account_id
        WHERE e.platform='spotify' ORDER BY ae.artist_id""").fetchall()
    assert [(l["artist_id"], l["platform_id"], l["collection_enabled"], l["is_primary"], l["position"]) for l in links] == [
        (a, A, False, True, 1), (b, C, False, True, 0)]
    assert q(database, "SELECT count(*) AS n FROM external_accounts WHERE platform='spotify'").fetchone()["n"] == 2
    assert sp.apply(database, decisions, write=True)["status"] == "already_committed"
    database.rollback()
    decisions["items"][0]["spotify_id"] = "B" * 22   # new manifest, but the artist is already linked
    decisions["items"][0]["version"] = q(database, "SELECT version FROM artists WHERE id=%s", (a,)).fetchone()["version"]
    with pytest.raises(RuntimeError, match="already has a Spotify link"):
        sp.apply(database, decisions, write=False)
    database.rollback()
