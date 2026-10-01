"""set_account_collection.py on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

from psycopg.rows import dict_row

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("set_account_collection", ROOT / "scripts/set_account_collection.py")
toggle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(toggle)


def q(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def test_turns_off_only_the_artists_accounts_with_audit(database):
    apply_schema(database)
    artist = row(database, "artists", slug="a", name_native="A", entity_kind="solo")
    other = row(database, "artists", slug="b", name_native="B", entity_kind="solo")
    mine = [row(database, "external_accounts", platform="x", platform_id=str(n), handle=f"a{n}",
                url=f"https://x.com/a{n}", collection_enabled=True) for n in (1, 2)]
    theirs = row(database, "external_accounts", platform="x", platform_id="3", handle="b",
                 url="https://x.com/b", collection_enabled=True)
    for account in mine:
        row(database, "artist_external_accounts", artist_id=artist, account_id=account, relationship="owner")
    row(database, "artist_external_accounts", artist_id=other, account_id=theirs, relationship="owner")
    database.commit()

    dry = toggle.apply(database, [artist], False, write=False)
    database.rollback()
    assert dry["status"] == "would_commit" and [a["id"] for a in dry["accounts"]] == mine
    result = toggle.apply(database, [artist], False, write=True)
    database.commit()
    assert result["status"] == "committed"
    flags = {r["id"]: r["collection_enabled"] for r in q(database, "SELECT id, collection_enabled FROM external_accounts")}
    assert flags == {mine[0]: False, mine[1]: False, theirs: True}
    changes = q(database, "SELECT action, before_data, after_data FROM catalog_changes WHERE import_id=%s",
                (result["import_id"],)).fetchall()
    assert len(changes) == 2 and all(c["action"] == "update" and c["before_data"]["collection_enabled"]
                                     and not c["after_data"]["collection_enabled"] for c in changes)
    assert toggle.apply(database, [artist], False, write=True)["status"] == "nothing_to_change"
    database.rollback()
