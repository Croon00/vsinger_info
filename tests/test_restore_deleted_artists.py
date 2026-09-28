"""restore_deleted_artists.py on disposable local PostgreSQL databases.

The "branch" is a copy of the catalog made before the deletion (CREATE DATABASE ... TEMPLATE);
the target then loses an artist the way production did on 2026-09-28: dependent rows deleted
in FK order, no catalog_changes.
"""
import importlib.util
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from test_catalog_migration import local_server, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("restore_deleted_artists", ROOT / "scripts/restore_deleted_artists.py")
restore = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(restore)


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


@pytest.fixture
def pair(local_server):
    names = ["catalog_" + uuid.uuid4().hex for _ in range(2)]
    dsn = lambda n: local_server.replace("dbname=postgres", "dbname=" + n)  # noqa: E731
    with psycopg.connect(local_server, autocommit=True) as control:
        control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(names[0])))
    with psycopg.connect(dsn(names[0])) as conn:
        apply_schema(conn)
        gone = row(conn, "artists", slug="gone", name_native="消えた", entity_kind="solo", show_in_catalog=True)
        other = row(conn, "artists", slug="other", name_native="残る", entity_kind="solo")
        song = row(conn, "songs", title_native="共作")
        row(conn, "song_artists", song_id=song, artist_id=other, position=0)
        row(conn, "song_artists", song_id=song, artist_id=gone, position=1)
        solo = row(conn, "songs", title_native="ソロ")
        row(conn, "song_artists", song_id=solo, artist_id=gone, position=0)
        account = row(conn, "external_accounts", platform="x", platform_id="77", handle="gone",
                      url="https://x.com/gone", collection_enabled=True)
        row(conn, "artist_external_accounts", artist_id=gone, account_id=account, relationship="owner")
        conn.execute("INSERT INTO collection_states(external_account_id,cursor_value) VALUES (%s,'9')", (account,))
        item = row(conn, "source_items", external_account_id=account, external_id="post-9",
                   source_url="https://x.com/gone/status/9", raw_text="kept", published_at="2026-09-21T00:00:00Z")
        conn.commit()
    with psycopg.connect(local_server, autocommit=True) as control:
        control.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(names[1]), sql.Identifier(names[0])))
    src, dst = psycopg.connect(dsn(names[0])), psycopg.connect(dsn(names[1]))
    for query in ["DELETE FROM source_items WHERE external_account_id=%(a)s",
                  "DELETE FROM collection_states WHERE external_account_id=%(a)s",
                  "DELETE FROM song_artists WHERE artist_id=%(g)s",
                  "DELETE FROM artist_external_accounts WHERE artist_id=%(g)s",
                  "DELETE FROM external_accounts WHERE id=%(a)s",
                  "DELETE FROM artists WHERE id=%(g)s"]:
        dst.execute(query, {"a": account, "g": gone})
    dst.commit()
    try:
        yield src, dst, {"gone": gone, "other": other, "song": song, "solo": solo, "account": account, "item": item}
    finally:
        src.close()
        dst.close()
        with psycopg.connect(local_server, autocommit=True) as control:
            for n in names:
                control.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(n)))


def decisions(ids, show=False):
    return {"policy": restore.POLICY, "artist_ids": [ids["gone"]], "show_in_catalog": show, "reason": "test"}


def test_restore_copies_deleted_rows_with_original_ids(pair):
    src, dst, ids = pair
    dry = restore.apply(src, dst, decisions(ids), write=False)
    dst.rollback()
    assert dry["status"] == "would_commit"
    assert {k: v for k, v in dry["counts"].items() if v} == {
        "artists": 1, "external_accounts": 1, "artist_external_accounts": 1, "song_artists": 2,
        "collection_states": 1, "source_items": 1}
    result = restore.apply(src, dst, decisions(ids), write=True)
    dst.commit()
    assert result["status"] == "committed"
    artist = q(dst, "SELECT name_native, show_in_catalog FROM artists WHERE id=%s", (ids["gone"],)).fetchone()
    assert artist == {"name_native": "消えた", "show_in_catalog": False}
    credits = q(dst, "SELECT song_id, artist_id, position FROM song_artists ORDER BY song_id, position").fetchall()
    assert [(c["song_id"], c["artist_id"], c["position"]) for c in credits] == [
        (ids["song"], ids["other"], 0), (ids["song"], ids["gone"], 1), (ids["solo"], ids["gone"], 0)]
    assert q(dst, "SELECT cursor_value FROM collection_states WHERE external_account_id=%s",
             (ids["account"],)).fetchone()["cursor_value"] == "9"
    assert q(dst, "SELECT id FROM source_items WHERE external_id='post-9'").fetchone()["id"] == ids["item"]
    changes = q(dst, "SELECT entity_type, action FROM catalog_changes WHERE import_id=%s", (result["import_id"],)).fetchall()
    assert len(changes) == 7 and {c["action"] for c in changes} == {"create"}
    assert restore.apply(src, dst, decisions(ids), write=True)["status"] == "already_committed"
    dst.rollback()


def test_refuses_artist_that_still_exists(pair):
    src, dst, ids = pair
    with pytest.raises(RuntimeError, match="still exist"):
        restore.apply(src, dst, {**decisions(ids), "artist_ids": [ids["other"]]}, write=False)
    dst.rollback()


def test_refuses_when_parent_row_is_gone(pair):
    src, dst, ids = pair
    dst.execute("DELETE FROM song_artists WHERE song_id=%s", (ids["solo"],))
    dst.execute("DELETE FROM songs WHERE id=%s", (ids["solo"],))
    dst.commit()
    with pytest.raises(RuntimeError, match="Parents of restored rows"):
        restore.apply(src, dst, decisions(ids), write=False)
    dst.rollback()
