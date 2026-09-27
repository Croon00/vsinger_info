"""Link unlinked performances to songs through confirmed song_match_keys (plan step 7).

Dry-run by default (READ ONLY transaction). ``--apply`` commits in buckets of
performance IDs; each bucket writes a catalog_imports receipt and one catalog_changes
row per performance, so every link can be traced and reversed. Only performances with
``song_id IS NULL`` whose normalized raw text equals a confirmed key (or, with no raw
artist, whose "title / artist" split equals confirmed keys of exactly one song) are
touched; raw text and existing links are never changed. Keys pointing at an archived
or merged-away song are skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import KEY_VERSION, lookup_keys, resolve_key  # noqa: E402

# v2 adds the "title / artist" split lookup (provenance.match = exact | split).
POLICY = "performance-song-link-from-match-keys-v2"
NAMESPACE = uuid.UUID("c2a7d0f4-1b9e-4e53-8a61-7f4d2e8b9c35")
BUCKET_SIZE = 2000

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query: str, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def collect(conn) -> dict:
    """Plan the links. Read-only."""
    keys = {(r["title_key"], r["artist_key"]): r for r in rows(conn, """
        SELECT k.id, k.title_key, k.artist_key, k.song_id FROM song_match_keys k
        JOIN songs s ON s.id=k.song_id AND s.archived_at IS NULL
        WHERE k.key_version=%s AND k.status='confirmed'
          AND NOT EXISTS (SELECT 1 FROM song_merges m WHERE m.source_song_id=k.song_id)""", (KEY_VERSION,))}
    candidates = rows(conn, """
        SELECT p.id, p.version, p.raw_title, p.raw_artist FROM performances p
        JOIN live_archives la ON la.id=p.archive_id AND la.archived_at IS NULL
        WHERE p.archived_at IS NULL AND p.song_id IS NULL ORDER BY p.id""").fetchall()
    links = []
    per_key: Counter = Counter()
    confirmed = {k: r["song_id"] for k, r in keys.items()}
    for p in candidates:
        # Same rule as the collection path: exact key, else an unambiguous split of "title / artist".
        lookup = lookup_keys(p["raw_title"], p["raw_artist"])
        resolved = resolve_key(lookup, confirmed)
        key = keys[resolved] if resolved else None
        if key:
            links.append({"id": p["id"], "version": p["version"], "song_id": key["song_id"], "key_id": key["id"],
                          "match": "exact" if resolved == lookup[0] else "split"})
            per_key[key["id"]] += 1
    buckets: dict[int, list[dict]] = defaultdict(list)
    for link in links:
        buckets[link["id"] // BUCKET_SIZE].append(link)
    return {"buckets": dict(sorted(buckets.items())),
            "summary": {"confirmed_keys": len(keys), "unlinked_performances": len(candidates),
                        "links": len(links), "keys_used": len(per_key), "buckets": len(buckets),
                        "still_unlinked": len(candidates) - len(links)}}


def apply_bucket(conn, catalog_id: str, bucket: int, links: list[dict]) -> tuple[str, int]:
    digest = hashlib.sha256(json.dumps({"policy": POLICY, "bucket": bucket, "links": links},
                                       sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    operation_id = uuid.uuid5(NAMESPACE, f"{catalog_id}:{POLICY}:{digest}")
    with conn.transaction():
        if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
            return "already_committed", 0
        updated = rows(conn, """
            UPDATE performances p SET song_id=x.song_id
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,song_id integer,key_id integer,match text)
            WHERE p.id=x.id AND p.version=x.version AND p.song_id IS NULL AND p.archived_at IS NULL
            RETURNING p.id, x.key_id, x.match, p.song_id, p.version""", (Jsonb(links),)).fetchall()
        if len(updated) != len(links):
            raise RuntimeError(f"Bucket {bucket}: performances changed since planning; rerun the dry-run")
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (operation_id, catalog_id, digest,
             Jsonb([{"entity_type": "performances", "id": r["id"], "version": r["version"]} for r in updated]),
             Jsonb({"kind": POLICY, "bucket": bucket, "linked": len(updated)}))).fetchone()[0]
        changes = [{"entity_id": r["id"], "before_data": {"song_id": None},
                    "after_data": {"song_id": r["song_id"]},
                    "provenance": {"policy": POLICY, "song_match_key_id": r["key_id"], "match": r["match"]}}
                   for r in updated]
        conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
            SELECT %s,'performances',x.entity_id,'update',x.before_data,x.after_data,x.provenance
            FROM jsonb_to_recordset(%s::jsonb) x(entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
            (import_id, Jsonb(changes)))
    return "committed", len(updated)


def check_target(conn) -> str:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    revisions = [r["version"] for r in rows(conn, "SELECT version FROM catalog_schema_migrations ORDER BY version")]
    if not identity or identity["schema_version"] != "catalog-v2" or "004" not in revisions:
        raise RuntimeError("Catalog must be catalog-v2 with revision 004 applied")
    return identity["id"]


def run(conn, *, write: bool) -> dict:
    """Plan in a read-only transaction; with ``write`` commit each bucket separately."""
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        catalog_id = check_target(conn)
        planned = collect(conn)
    result = {"mode": "apply" if write else "dry-run", **planned["summary"]}
    if write:
        statuses: Counter = Counter()
        linked = 0
        for bucket, links in planned["buckets"].items():
            status, count = apply_bucket(conn, catalog_id, bucket, links)
            statuses[status] += 1
            linked += count
        result.update(linked=linked, bucket_status=dict(statuses))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit links bucket by bucket with receipts")
    args = parser.parse_args()
    uri = migrate_catalog.load_connection()
    with psycopg.connect(uri, connect_timeout=20, autocommit=True) as conn:
        conn.execute("SET statement_timeout='120s'")
        conn.execute("SET lock_timeout='10s'")
        conn.execute("SET idle_in_transaction_session_timeout='60s'")
        result = run(conn, write=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
