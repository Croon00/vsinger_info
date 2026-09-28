"""Restore artists deleted outside the catalog tools, copying their rows from a Neon branch.

Source: a Neon branch made at a point in time BEFORE the deletion, given as the
RESTORE_SOURCE_DATABASE_URL environment variable. It is only read (READ ONLY transaction).
Target: the production catalog (DATABASE_URL).

Decision file: migrations/catalog/artist-restores-N.json
  {"policy": "deleted-artist-restore-v1", "artist_ids": [1, 2],
   "show_in_catalog": false, "reason": "..."}

What is restored: every row of the listed artists, and of their external accounts, that
exists in the branch and no longer exists in production (primary key missing): artists,
external_accounts, artist_external_accounts, artist_aliases, artist_group_members, the
credit tables (song/performance/archive/concert/album/recording/cover artists),
collection_states and source_items. Rows keep their original ids. worker_jobs are not
restored: they are run history, and restoring pending ones would restart collection.

Refusals: a listed artist that still exists in production, or is missing from the branch;
a restored row whose parent (song, performance, album, ...) is gone from production.

Default is a READ ONLY dry-run. ``--apply`` writes ONE transaction under one catalog_imports
receipt (source_kind 'correction'); each inserted row is a catalog_changes 'create' with the
branch as provenance. Artists get show_in_catalog from the decision file. Rerunning the same
file is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POLICY = "deleted-artist-restore-v1"
NAMESPACE = uuid.UUID("0d7c3e51-6a2f-4b89-9e14-c5a8f2d07b36")
LOCK_ID = 731064923  # shared with the other catalog writers
SOURCE_ENV = "RESTORE_SOURCE_DATABASE_URL"

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)

# (table, primary key, selection over the branch, parent checks in production).
# Order is insert order: parents before children.
ARTIST_TABLES = [
    ("artist_aliases", "id", "artist_id = ANY(%(artists)s)", []),
    ("artist_group_members", "id", "member_id = ANY(%(artists)s) OR group_id = ANY(%(artists)s)",
     [("member_id", "artists"), ("group_id", "artists")]),
    ("song_artists", "id", "artist_id = ANY(%(artists)s)", [("song_id", "songs")]),
    ("performance_artists", "id", "artist_id = ANY(%(artists)s)", [("performance_id", "performances")]),
    ("archive_artists", "id", "artist_id = ANY(%(artists)s)", [("archive_id", "live_archives")]),
    ("concert_artists", "id", "artist_id = ANY(%(artists)s)", [("concert_id", "concerts")]),
    ("album_artists", "id", "artist_id = ANY(%(artists)s)", [("album_id", "albums")]),
    ("recording_artists", "id", "artist_id = ANY(%(artists)s)", [("recording_id", "recordings")]),
    ("cover_artists", "id", "artist_id = ANY(%(artists)s)", [("cover_id", "covers")]),
]
ACCOUNT_TABLES = [
    ("collection_states", "external_account_id", "external_account_id = ANY(%(accounts)s)", []),
    ("source_items", "id", "external_account_id = ANY(%(accounts)s)", []),
]


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def manifest(decisions: dict) -> str:
    body = {k: decisions.get(k) for k in ("policy", "artist_ids", "show_in_catalog")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def columns(conn, table: str) -> list[str]:
    return [r["column_name"] for r in rows(conn, """SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""", (table,))]


def existing(conn, table: str, key: str, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    return {r["k"] for r in rows(conn, f'SELECT "{key}" AS k FROM "{table}" WHERE "{key}" = ANY(%s)', (ids,))}


def branch_rows(src, table: str, key: str, where: str, params: dict) -> list[dict]:
    return [r["j"] for r in rows(src, f'SELECT to_jsonb(t) AS j FROM "{table}" t WHERE {where} ORDER BY t."{key}"', params)]


def plan(src, dst, decisions: dict) -> dict:
    artist_ids = sorted(decisions["artist_ids"])
    in_branch = existing(src, "artists", "id", artist_ids)
    still_there = existing(dst, "artists", "id", artist_ids)
    if set(artist_ids) - in_branch:
        raise RuntimeError(f"Artists missing from the branch: {sorted(set(artist_ids) - in_branch)}")
    if still_there:
        raise RuntimeError(f"Artists still exist in production: {sorted(still_there)}")
    for table in ["artists", "external_accounts"] + [t for t, *_ in ARTIST_TABLES + ACCOUNT_TABLES]:
        if columns(src, table) != columns(dst, table):
            raise RuntimeError(f"Column layout differs between branch and production: {table}")

    out: dict[str, list[dict]] = {}
    out["artists"] = branch_rows(src, "artists", "id", "id = ANY(%(artists)s)", {"artists": artist_ids})
    links = branch_rows(src, "artist_external_accounts", "id", "artist_id = ANY(%(artists)s)", {"artists": artist_ids})
    account_ids = sorted({r["account_id"] for r in links})
    kept_accounts = existing(dst, "external_accounts", "id", account_ids)
    restore_accounts = [a for a in account_ids if a not in kept_accounts]
    out["external_accounts"] = branch_rows(src, "external_accounts", "id", "id = ANY(%(accounts)s)",
                                           {"accounts": restore_accounts})
    have_links = existing(dst, "artist_external_accounts", "id", [r["id"] for r in links])
    out["artist_external_accounts"] = [r for r in links if r["id"] not in have_links]

    params = {"artists": artist_ids, "accounts": restore_accounts}
    orphans: dict[str, list[int]] = {}
    for table, key, where, parents in ARTIST_TABLES + ACCOUNT_TABLES:
        found = branch_rows(src, table, key, where, params)
        have = existing(dst, table, key, [r[key] for r in found])
        missing = [r for r in found if r[key] not in have]
        for column, parent in parents:
            refs = sorted({r[column] for r in missing if r[column] is not None and r[column] not in artist_ids})
            if parent == "artists":
                continue  # group members may point at the restored artists themselves; FK checks the rest
            gone = set(refs) - existing(dst, parent, "id", refs)
            if gone:
                orphans[f"{table}.{column}"] = sorted(gone)
        out[table] = missing
    if orphans:
        raise RuntimeError(f"Parents of restored rows are gone from production: {orphans}")
    return {"rows": out, "restore_accounts": restore_accounts, "kept_accounts": sorted(kept_accounts)}


def summarize(result: dict) -> dict:
    rows_ = result["rows"]
    accounts = rows_["external_accounts"]
    return {
        "counts": {t: len(v) for t, v in rows_.items()},
        "artists": [{"id": r["id"], "name_native": r["name_native"], "show_in_catalog_before": r["show_in_catalog"]}
                    for r in rows_["artists"]],
        "accounts": [{"id": r["id"], "platform": r["platform"], "platform_id": r["platform_id"],
                      "collection_enabled": r["collection_enabled"]} for r in accounts],
        "accounts_kept_in_production": result["kept_accounts"],
    }


def insert(dst, table: str, data: list[dict]) -> None:
    if not data:
        return
    cols = ", ".join(f'"{c}"' for c in columns(dst, table))
    dst.execute(f'INSERT INTO "{table}" ({cols}) OVERRIDING SYSTEM VALUE '
                f'SELECT {cols} FROM jsonb_populate_recordset(NULL::"{table}", %s)', (Jsonb(data),))


def apply(src, dst, decisions: dict, *, write: bool) -> dict:
    identity = rows(dst, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    if identity["schema_version"] != "catalog-v2":
        raise RuntimeError("Catalog must be catalog-v2")
    if decisions.get("policy") != POLICY or not decisions.get("artist_ids"):
        raise RuntimeError("Unexpected decision file policy, or no artist_ids")
    if not isinstance(decisions.get("show_in_catalog"), bool):
        raise RuntimeError("show_in_catalog must be true or false")
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest)
    if write:
        dst.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    if dst.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    result = plan(src, dst, decisions)
    summary = summarize(result)
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, **summary}

    show = decisions["show_in_catalog"]
    for r in result["rows"]["artists"]:
        r["show_in_catalog"] = show
    order = ["artists", "external_accounts", "artist_external_accounts"] + [t for t, *_ in ARTIST_TABLES + ACCOUNT_TABLES]
    for table in order:
        insert(dst, table, result["rows"][table])
    import_id = dst.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
        (operation_id, identity["id"], digest, Jsonb([{"artist_id": a} for a in sorted(decisions["artist_ids"])]),
         Jsonb({"kind": POLICY, "counts": summary["counts"], "show_in_catalog": show}))).fetchone()[0]
    provenance = {"policy": POLICY, "source": "neon-branch", "reason": decisions.get("reason")}
    keys = {"collection_states": "external_account_id"}
    changes = [{"entity_type": table, "entity_id": r[keys.get(table, "id")], "after_data": r, "provenance": provenance}
               for table in order for r in result["rows"][table]]
    dst.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,x.entity_type,x.entity_id,'create',NULL,x.after_data,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_type text,entity_id integer,after_data jsonb,provenance jsonb)""",
                (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="Decision file, e.g. migrations/catalog/artist-restores-1.json")
    parser.add_argument("--apply", action="store_true", help="Insert the rows in one transaction")
    args = parser.parse_args()
    source_url = os.environ.get(SOURCE_ENV)
    if not source_url:
        raise SystemExit(f"Set {SOURCE_ENV} to the branch connection string")
    decisions = json.loads(args.file.read_text(encoding="utf-8"))
    with psycopg.connect(source_url, connect_timeout=20) as src, \
            psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as dst:
        src.execute("SET TRANSACTION READ ONLY")
        migrate_catalog.configure_transaction(dst, read_only=not args.apply)
        result = apply(src, dst, decisions, write=args.apply)
        src.rollback()
        if args.apply:
            dst.commit()
        else:
            dst.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
