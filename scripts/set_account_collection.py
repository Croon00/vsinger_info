"""Turn collection on or off for every external account linked to the given artists.

Usage: set_account_collection.py --artists 1,2 --off [--apply]
       set_account_collection.py --artists 1,2 --on  [--apply]

Default is a READ ONLY dry-run listing the accounts whose flag would change. ``--apply``
updates external_accounts.collection_enabled in ONE transaction under one catalog_imports
receipt (source_kind 'manual'), and keeps each row's before/after in catalog_changes.
Workers check the flag when they enqueue and claim, so queued jobs of a disabled account
stop running. Accounts already in the requested state are left alone; a rerun is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POLICY = "account-collection-toggle-v1"
NAMESPACE = uuid.UUID("5f9a2c7e-1b34-4d6a-8e0f-73c1b9d2a4e8")
LOCK_ID = 731064923  # shared with the other catalog writers

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def apply(conn, artist_ids: list[int], enabled: bool, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    found = {r["id"] for r in rows(conn, "SELECT id FROM artists WHERE id=ANY(%s)", (artist_ids,))}
    if set(artist_ids) - found:
        raise RuntimeError(f"Artists not found: {sorted(set(artist_ids) - found)}")
    targets = rows(conn, """SELECT e.id, e.platform, e.platform_id, e.handle, to_jsonb(e) AS before
        FROM external_accounts e
        WHERE EXISTS (SELECT 1 FROM artist_external_accounts ae WHERE ae.account_id=e.id AND ae.artist_id=ANY(%s))
          AND e.collection_enabled IS DISTINCT FROM %s ORDER BY e.id"""
                   + (" FOR UPDATE" if write else ""), (artist_ids, enabled)).fetchall()
    listing = [{"id": t["id"], "platform": t["platform"], "platform_id": t["platform_id"], "handle": t["handle"]}
               for t in targets]
    if not targets:
        return {"status": "nothing_to_change", "enabled": enabled}
    if not write:
        return {"status": "would_commit", "enabled": enabled, "accounts": listing}
    ids = [t["id"] for t in targets]
    conn.execute("UPDATE external_accounts SET collection_enabled=%s WHERE id=ANY(%s)", (enabled, ids))
    after = {r["id"]: r["j"] for r in rows(conn, "SELECT id, to_jsonb(e) AS j FROM external_accounts e WHERE id=ANY(%s)", (ids,))}
    body = {"policy": POLICY, "artist_ids": sorted(artist_ids), "enabled": enabled, "accounts": ids,
            "versions": [t["before"]["version"] for t in targets]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'manual',%s,%s) RETURNING id""",
        (uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest), identity["id"], digest,
         Jsonb([{"account_id": i} for i in ids]),
         Jsonb({"kind": POLICY, "artist_ids": sorted(artist_ids), "enabled": enabled, "accounts": len(ids)}))).fetchone()[0]
    changes = [{"entity_id": t["id"], "before_data": t["before"], "after_data": after[t["id"]]} for t in targets]
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,'external_accounts',x.entity_id,'update',x.before_data,x.after_data,%s
        FROM jsonb_to_recordset(%s::jsonb) x(entity_id integer,before_data jsonb,after_data jsonb)""",
                 (import_id, Jsonb({"policy": POLICY}), Jsonb(changes)))
    return {"status": "committed", "import_id": import_id, "enabled": enabled, "accounts": listing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artists", required=True, help="Comma-separated artist ids")
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--on", action="store_true", help="Enable collection")
    state.add_argument("--off", action="store_true", help="Disable collection")
    parser.add_argument("--apply", action="store_true", help="Write in one transaction")
    args = parser.parse_args()
    artist_ids = sorted({int(x) for x in args.artists.split(",") if x.strip()})
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not args.apply)
        result = apply(conn, artist_ids, args.on, write=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
