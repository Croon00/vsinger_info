"""Temporarily assign each imported setlist performance to its archive's host.

The user explicitly requested this provisional attribution. Dry-run by default.
Each 2,000-ID bucket is committed with a receipt and row-level audit trail.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import uuid

import psycopg
from psycopg.types.json import Jsonb

from import_legacy_setlists import NAMESPACE, connection_url, digest


VERSION = "provisional-host-singer-v1"
BUCKET_SIZE = 2000


def candidates(conn) -> tuple[str, dict[int, list[tuple[int, int]]]]:
    identity = conn.execute("SELECT id,schema_version FROM catalog_instance").fetchone()
    if not identity or identity[1] != "catalog-v1":
        raise ValueError("Unexpected catalog identity")
    rows = conn.execute("""SELECT p.id,l.primary_artist_id FROM performances p
        JOIN live_archives l ON l.id=p.archive_id
        JOIN archive_artists a ON a.archive_id=l.id AND a.artist_id=l.primary_artist_id
        WHERE p.archived_at IS NULL AND l.archived_at IS NULL
        ORDER BY p.id""").fetchall()
    grouped = defaultdict(list)
    for performance_id, artist_id in rows:
        grouped[performance_id // BUCKET_SIZE].append((performance_id, artist_id))
    return str(identity[0]), grouped


def apply_bucket(conn, catalog_id: str, bucket: int, entries: list[tuple[int, int]]) -> tuple[str, int]:
    manifest_hash = digest({"version": VERSION, "catalog_id": catalog_id,
                            "bucket": bucket, "entries": entries})
    operation_id = uuid.uuid5(NAMESPACE, catalog_id + ":" + VERSION + ":" + str(bucket))
    with conn.transaction():
        conn.execute("SET LOCAL search_path=public")
        conn.execute("SET LOCAL statement_timeout='120s'")
        conn.execute("SET LOCAL lock_timeout='10s'")
        receipt = conn.execute("SELECT manifest_hash FROM catalog_imports WHERE operation_id=%s",
                               (operation_id,)).fetchone()
        if receipt:
            if receipt[0] != manifest_hash:
                raise ValueError("Provisional singer receipt manifest changed")
            return "already_committed", 0
        ids = [entry[0] for entry in entries]
        present = conn.execute("""SELECT performance_id FROM performance_artists
            WHERE performance_id=ANY(%s)""", (ids,)).fetchall()
        present_ids = {value[0] for value in present}
        missing = [{"performance_id": pid, "artist_id": artist_id}
                   for pid, artist_id in entries if pid not in present_ids]
        if not missing:
            return "already_attributed", 0
        inserted = conn.execute("""INSERT INTO performance_artists
            (performance_id,artist_id,role,position)
            SELECT x.performance_id,x.artist_id,'lead',0
            FROM jsonb_to_recordset(%s::jsonb) x(performance_id integer,artist_id integer)
            WHERE NOT EXISTS (SELECT 1 FROM performance_artists pa
              WHERE pa.performance_id=x.performance_id)
            RETURNING id,performance_id,to_jsonb(performance_artists)""",
            (Jsonb(missing),)).fetchall()
        if len(inserted) != len(missing):
            raise ValueError("Concurrent singer assignment changed the batch")
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (operation_id, catalog_id, manifest_hash,
             Jsonb([{"entity_type": "performance_artists", "performance_id": pid,
                     "new_id": artist_link_id} for artist_link_id, pid, _ in inserted]),
             Jsonb({"kind": VERSION, "bucket": bucket, "inserted": len(inserted),
                    "already_attributed": len(present_ids),
                    "policy": "Temporary attribution to the archive primary artist by user request"}))).fetchone()[0]
        changes = [{"entity_id": artist_link_id, "after_data": data,
                    "provenance": {"performance_id": pid, "policy": VERSION,
                                   "review_status": "provisional"}}
                   for artist_link_id, pid, data in inserted]
        conn.execute("""INSERT INTO catalog_changes
            (import_id,entity_type,entity_id,action,after_data,provenance)
            SELECT %s,'performance_artists',entity_id,'create',after_data,provenance
            FROM jsonb_to_recordset(%s::jsonb)
              x(entity_id integer,after_data jsonb,provenance jsonb)""",
            (import_id, Jsonb(changes)))
    return "committed", len(inserted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with psycopg.connect(connection_url(), connect_timeout=10, autocommit=True,
                         prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            catalog_id, batches = candidates(conn)
            existing = conn.execute("SELECT count(*) FROM performance_artists").fetchone()[0]
        print(json.dumps({"catalog_id": catalog_id, "eligible": sum(map(len, batches.values())),
                          "batches": len(batches), "existing_links": existing}), flush=True)
        if not args.apply:
            return
        inserted_total = 0
        for bucket, entries in sorted(batches.items()):
            status, inserted = apply_bucket(conn, catalog_id, bucket, entries)
            inserted_total += inserted
            print(json.dumps({"bucket": bucket, "status": status, "inserted": inserted}), flush=True)
        print(json.dumps({"inserted_total": inserted_total}), flush=True)


if __name__ == "__main__":
    main()
