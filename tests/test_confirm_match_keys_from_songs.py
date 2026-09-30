"""Confirming pending match keys against existing songs, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from test_catalog_migration import local_server, database, apply as apply_schema, row, artist  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("confirm_keys", ROOT / "scripts/confirm_match_keys_from_songs.py")
ck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ck)


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def key(conn, title, artist_key, raw_title=None, raw_artist=None):
    return row(conn, "song_match_keys", title_key=title, artist_key=artist_key,
               sample_raw_title=raw_title or title, sample_raw_artist=raw_artist, occurrence_count=1)


def song(conn, title, *artist_ids):
    s = row(conn, "songs", title_native=title)
    for n, a in enumerate(artist_ids):
        row(conn, "song_artists", song_id=s, artist_id=a, position=n)
    return s


@pytest.fixture
def catalog(database):
    apply_schema(database)
    conn = database
    yono = artist(conn, "yono", name_latin="Yono")
    conn.execute("UPDATE artists SET name_native='ヨノ' WHERE id=%s", (yono,))
    hachi = artist(conn, "hachi-a", name_latin="HACHI")
    conn.execute("UPDATE artists SET name_native='HACHI' WHERE id=%s", (hachi,))
    hachi_v = artist(conn, "hachi-v", name_latin="Hachi")
    conn.execute("UPDATE artists SET name_native='ハチ' WHERE id=%s", (hachi_v,))
    matsu = artist(conn, "matsu")
    conn.execute("UPDATE artists SET name_native='松永依織' WHERE id=%s", (matsu,))
    ids = {"flower": song(conn, "花に落ちる", yono), "awaken": song(conn, "Awaken Now", matsu),
           "beedama": song(conn, "ビー玉", hachi), "old": song(conn, "砂の惑星", hachi_v),
           "dup_new": song(conn, "Rain", yono), "dup_old": song(conn, "Rain", yono)}
    imp = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind)
        SELECT gen_random_uuid(), id, repeat('a',64), 'batch_import' FROM catalog_instance RETURNING id""").fetchone()[0]
    for name in ("flower", "awaken", "beedama", "dup_new"):
        conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,after_data)
            VALUES (%s,'songs',%s,'create',%s)""", (imp, ids[name], Jsonb({})))
    ids["k_exact"] = key(conn, "花に落ちる", "ヨノ")
    ids["k_space"] = key(conn, "awaken now", "松永 依織", "Awaken Now", "松永 依織")
    ids["k_latin"] = key(conn, "ビー玉", "hachi")                         # HACHI native beats ハチ's Latin name
    ids["k_split"] = key(conn, "花に落ちる / ヨノ", "", "花に落ちる / ヨノ")
    ids["k_old"] = key(conn, "砂の惑星", "ハチ")                            # older song: outside --import-id
    ids["k_dup"] = key(conn, "rain", "ヨノ")                                # a new AND an older song
    ids["k_other"] = key(conn, "花に落ちる", "someone")
    ids["k_title_only"] = key(conn, "ビー玉", "")
    video = row(conn, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive")
    archive = row(conn, "live_archives", video_id=video)
    for n, (title, art) in enumerate([("花に落ちる", "ヨノ"), ("花に落ちる", "ヨノ"), ("花に落ちる / ヨノ", None),
                                       ("Awaken Now", "松永 依織"), ("砂の惑星", "ハチ")], 1):
        row(conn, "performances", archive_id=archive, ordinal=n, start_seconds=n * 10, raw_title=title, raw_artist=art)
    conn.commit()
    return conn, ids, imp


def test_plan_matches_exact_loose_and_split_keys(catalog):
    conn, ids, imp = catalog
    state = ck.load_state(conn, imp)
    conn.rollback()
    decisions = ck.plan(state)
    confirm = {c["key_id"]: c for c in decisions["confirm"]}
    assert set(confirm) == {ids["k_exact"], ids["k_space"], ids["k_latin"], ids["k_split"]}
    assert confirm[ids["k_latin"]]["song_id"] == ids["beedama"]
    assert (confirm[ids["k_split"]]["basis"], confirm[ids["k_split"]]["song_id"]) == ("split", ids["flower"])
    assert [r["key_id"] for r in decisions["review"]] == [ids["k_dup"]]
    assert confirm[ids["k_exact"]]["would_link"] == 2 and confirm[ids["k_split"]]["would_link"] == 1
    assert decisions["summary"]["would_link_performances"] == 4
    everything = ck.plan(ck.load_state(conn))                               # no import filter
    conn.rollback()
    assert ids["k_old"] in {c["key_id"] for c in everything["confirm"]}


def test_review_and_apply(catalog, tmp_path):
    conn, ids, imp = catalog
    decisions = ck.plan(ck.load_state(conn, imp))
    conn.rollback()
    text = ck.render_review(decisions, "d.json")
    # The user drops the split key and picks the older Rain song for the ambiguous key.
    text = text.replace(f"| song:{ids['flower']} | {ids['flower']} 花に落ちる / ヨノ | split |",
                        f"| - | {ids['flower']} 花に落ちる / ヨノ | split |")
    def decide(line):
        cells = line.split(" | ")
        cells[4] = f"song:{ids['dup_old']}"
        return " | ".join(cells)

    lines = [decide(line) if line.startswith(f"| {ids['k_dup']} |") else line for line in text.splitlines()]
    review = tmp_path / "review.md"
    review.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reviewed, changes = ck.apply_review(decisions, ck.read_review(review))
    assert {c["key_id"] for c in changes} == {ids["k_split"], ids["k_dup"]}
    assert ck.apply(conn, reviewed, write=False)["status"] == "would_commit"
    conn.rollback()
    result = ck.apply(conn, reviewed, write=True)
    conn.commit()
    assert (result["status"], result["keys"]) == ("committed", 4)
    got = {r["id"]: r for r in q(conn, "SELECT id, status, song_id, decided_by FROM song_match_keys")}
    assert (got[ids["k_dup"]]["song_id"], got[ids["k_dup"]]["decided_by"]) == (ids["dup_old"], "manual")
    assert (got[ids["k_exact"]]["status"], got[ids["k_exact"]]["decided_by"]) == ("confirmed", "existing_link")
    assert got[ids["k_split"]]["status"] == "pending" and got[ids["k_title_only"]]["status"] == "pending"
    assert q(conn, "SELECT count(*) n FROM catalog_changes WHERE entity_type='song_match_keys'").fetchone()["n"] == 4
    assert ck.apply(conn, reviewed, write=True)["status"] == "already_committed"
    conn.rollback()
    stale = ck.plan(ck.load_state(conn))
    conn.rollback()
    conn.execute("UPDATE song_match_keys SET occurrence_count=5 WHERE id=%s", (ids["k_old"],))
    conn.commit()
    with pytest.raises(RuntimeError, match="changed since export"):
        ck.apply(conn, stale, write=False)
    conn.rollback()
