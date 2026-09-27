"""Merging duplicate artists and songs, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("merge", ROOT / "scripts/merge_catalog_entities.py")
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


@pytest.fixture
def catalog(database):
    apply_schema(database)
    koyori = row(database, "artists", slug="koyori", name_native="koyori", entity_kind="solo")
    denpo = row(database, "artists", slug="denporu-p", name_native="電ポルP", name_latin="Denporu P", entity_kind="solo")
    oe = row(database, "artists", slug="oe", name_native="大江千里", entity_kind="solo")
    hata = row(database, "artists", slug="hata", name_native="秦基博", entity_kind="solo")
    row(database, "artist_aliases", artist_id=denpo, alias="Denpol P", normalized_alias="denpol p")
    rain, rain2, envy, lover = (row(database, "songs", title_native=t) for t in ("Rain", "Rain", "独りんぼエンヴィー", "曖昧劣情Lover"))
    for song, artist in ((rain, oe), (rain2, hata), (rain2, oe), (envy, denpo), (lover, koyori), (lover, denpo)):
        row(database, "song_artists", song_id=song, artist_id=artist)
    row(database, "song_external_ids", song_id=rain, provider="musicbrainz_work", external_id="b86800d4-00e8-4496-899f-5bba0bc1bb41")
    key = row(database, "song_match_keys", title_key="rain", artist_key="秦基博", sample_raw_title="Rain", status="confirmed",
              song_id=rain2, decided_by="manual", decided_at="2026-09-27T00:00:00Z")
    video = row(database, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive")
    archive = row(database, "live_archives", video_id=video, primary_artist_id=denpo)
    perf = row(database, "performances", archive_id=archive, ordinal=1, start_seconds=10, raw_title="Rain", song_id=rain2)
    database.commit()
    return database, {"koyori": koyori, "denpo": denpo, "oe": oe, "hata": hata, "rain": rain, "rain2": rain2,
                      "envy": envy, "lover": lover, "key": key, "archive": archive, "perf": perf}


def decisions(ids):
    return {"policy": merge.POLICY, "artists": [{"source": ids["denpo"], "target": ids["koyori"], "reason": "same person"}],
            "songs": [{"source": ids["rain2"], "target": ids["rain"], "reason": "same work"}]}


def test_dry_run_counts_without_writing(catalog):
    conn, ids = catalog
    result = merge.apply(conn, decisions(ids), write=False)
    conn.rollback()
    artist = result["merges"][f"artists:{ids['denpo']}->{ids['koyori']}"]
    assert artist["song_artists.artist_id"] == {"moved": 1, "deleted": 1}   # 曖昧劣情Lover already credits koyori
    assert artist["aliases_added"] == ["電ポルP", "Denporu P"]
    song = result["merges"][f"songs:{ids['rain2']}->{ids['rain']}"]
    assert song["performances.song_id"] == {"moved": 1, "deleted": 0} and song["song_artists.song_id"] == {"moved": 1, "deleted": 1}
    assert q(conn, "SELECT count(*) AS n FROM songs WHERE archived_at IS NOT NULL").fetchone()["n"] == 0


def test_apply_repoints_everything_once_with_audit(catalog):
    conn, ids = catalog
    result = merge.apply(conn, decisions(ids), write=True)
    conn.commit()
    assert result["status"] == "committed"
    credits = {(r["song_id"], r["artist_id"]) for r in q(conn, "SELECT song_id, artist_id FROM song_artists")}
    assert credits == {(ids["rain"], ids["oe"]), (ids["rain"], ids["hata"]), (ids["envy"], ids["koyori"]),
                       (ids["lover"], ids["koyori"])}
    order = [r["artist_id"] for r in q(conn, "SELECT artist_id FROM song_artists WHERE song_id=%s ORDER BY position, id", (ids["rain"],))]
    assert order == [ids["oe"], ids["hata"]] and q(conn, "SELECT max(position) AS p FROM song_artists WHERE song_id=%s",
                                                    (ids["rain"],)).fetchone()["p"] == 1
    aliases = {r["alias"] for r in q(conn, "SELECT alias FROM artist_aliases WHERE artist_id=%s", (ids["koyori"],))}
    assert aliases == {"Denpol P", "電ポルP", "Denporu P"}
    assert q(conn, "SELECT primary_artist_id FROM live_archives").fetchone()["primary_artist_id"] == ids["koyori"]
    assert q(conn, "SELECT song_id FROM performances").fetchone()["song_id"] == ids["rain"]
    assert q(conn, "SELECT song_id FROM song_match_keys").fetchone()["song_id"] == ids["rain"]
    archived = {r["id"] for r in q(conn, "SELECT id FROM artists WHERE archived_at IS NOT NULL")} | \
               {r["id"] for r in q(conn, "SELECT id FROM songs WHERE archived_at IS NOT NULL")}
    assert archived == {ids["denpo"], ids["rain2"]}
    assert q(conn, "SELECT source_song_id, target_song_id FROM song_merges").fetchone() == {
        "source_song_id": ids["rain2"], "target_song_id": ids["rain"]}
    changes = q(conn, "SELECT entity_type, action, provenance FROM catalog_changes ORDER BY id").fetchall()
    assert [(c["entity_type"], c["action"]) for c in changes] == [("artists", "merge"), ("songs", "merge")]
    assert changes[0]["provenance"]["refs"]["song_artists.artist_id"]["deleted"][0]["song_id"] == ids["lover"]
    assert merge.apply(conn, decisions(ids), write=True)["status"] == "already_committed"
    conn.rollback()


def test_chains_and_archived_sides_are_refused(catalog):
    conn, ids = catalog
    chain = {"policy": merge.POLICY, "artists": [{"source": ids["denpo"], "target": ids["koyori"], "reason": "x"},
                                                 {"source": ids["koyori"], "target": ids["oe"], "reason": "x"}]}
    with pytest.raises(RuntimeError, match="chain"):
        merge.apply(conn, chain, write=False)
    conn.rollback()
    conn.execute("UPDATE artists SET archived_at=clock_timestamp() WHERE id=%s", (ids["koyori"],))
    conn.commit()
    with pytest.raises(RuntimeError, match="archived"):
        merge.apply(conn, {"policy": merge.POLICY, "artists": decisions(ids)["artists"]}, write=False)
    conn.rollback()
