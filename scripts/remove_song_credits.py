"""Remove song credits (song_artists rows) that name the wrong artist.

Decision file: migrations/catalog/song-credit-removals-N.json
  {"policy": "song-credit-removal-v1",
   "removals": [{"song_id": 1646, "artist_id": 638, "reason": "..."}]}

Default is a READ ONLY dry-run. ``--apply`` writes ONE transaction: each listed credit is
deleted, the song's remaining credits keep their order with positions renumbered from 0,
and catalog_changes keeps every deleted row under one catalog_imports receipt
(source_kind 'correction'). A credit that is missing, a song that would be left without
credits, or a duplicate entry refuses the whole file. Rerunning the same file is a no-op.
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

POLICY = "song-credit-removal-v1"
NAMESPACE = uuid.UUID("6b1e4f2a-93c7-4d58-a0e6-2f7c9d4b8a13")
LOCK_ID = 731064923  # shared with the other catalog writers

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def manifest(decisions: dict) -> str:
    body = {k: decisions.get(k) for k in ("policy", "removals")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def apply(conn, decisions: dict, *, write: bool) -> dict:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    if identity["schema_version"] != "catalog-v2":
        raise RuntimeError("Catalog must be catalog-v2")
    if decisions.get("policy") != POLICY:
        raise RuntimeError("Unexpected decision file policy")
    removals = decisions.get("removals") or []
    pairs = [(r["song_id"], r["artist_id"]) for r in removals]
    if not pairs or len(set(pairs)) != len(pairs):
        raise RuntimeError("No removals, or a credit is listed twice")
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, identity["id"] + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    song_ids = sorted({s for s, _ in pairs})
    credits = rows(conn, "SELECT * FROM song_artists WHERE song_id=ANY(%s) ORDER BY song_id, position, id"
                   + (" FOR UPDATE" if write else ""), (song_ids,)).fetchall()
    by_pair = {(c["song_id"], c["artist_id"]): c for c in credits}
    missing = [list(p) for p in pairs if p not in by_pair]
    if missing:
        raise RuntimeError(f"Credits not found: {missing}")
    remove = set(pairs)
    left = {s: [c for c in credits if c["song_id"] == s and (s, c["artist_id"]) not in remove] for s in song_ids}
    empty = [s for s, kept in left.items() if not kept]
    if empty:
        raise RuntimeError(f"Songs would be left without credits: {empty}")
    plan = [{"song_id": s, "removed": [c["artist_id"] for c in credits if c["song_id"] == s and (s, c["artist_id"]) in remove],
             "kept": [c["artist_id"] for c in left[s]]} for s in song_ids]
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, "credits": len(pairs), "songs": plan}
    deleted = [by_pair[p] for p in pairs]
    conn.execute("DELETE FROM song_artists WHERE id=ANY(%s)", ([c["id"] for c in deleted],))
    for kept in left.values():
        for n, c in enumerate(kept):
            if c["position"] != n:
                conn.execute("UPDATE song_artists SET position=%s WHERE id=%s", (n, c["id"]))
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
        (operation_id, identity["id"], digest, Jsonb([{"song_id": s, "artist_id": a} for s, a in pairs]),
         Jsonb({"kind": POLICY, "credits": len(pairs), "songs": len(song_ids)}))).fetchone()[0]
    reasons = {(r["song_id"], r["artist_id"]): r["reason"] for r in removals}
    changes = [{"entity_id": c["id"], "before_data": json.loads(json.dumps(c, default=str)),
                "provenance": {"policy": POLICY, "reason": reasons[(c["song_id"], c["artist_id"])]}} for c in deleted]
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,'song_artists',x.entity_id,'delete',x.before_data,NULL,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_id integer,before_data jsonb,provenance jsonb)""",
                 (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, "credits": len(pairs), "songs": plan}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="Decision file, e.g. migrations/catalog/song-credit-removals-1.json")
    parser.add_argument("--apply", action="store_true", help="Delete the credits in one transaction")
    args = parser.parse_args()
    decisions = json.loads(args.file.read_text(encoding="utf-8"))
    with psycopg.connect(migrate_catalog.load_connection(), connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not args.apply)
        result = apply(conn, decisions, write=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
