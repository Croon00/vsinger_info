"""Aggregate setlist raw text into song_match_keys (song-master plan step 4).

Dry-run by default: reads in a READ ONLY transaction and prints the plan summary.
``--apply`` writes one transaction with a catalog_imports receipt. It never changes
performances or songs; it only records keys and derives these states from links
that already exist in performances:

- every performance of the key is linked to one song  -> confirmed (existing_link)
- linked performances point to several songs          -> ambiguous (existing_link)
- anything else                                        -> pending (candidate in evidence)

Manual/provider decisions are never overwritten; only counts and samples refresh.
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

from app.core.song_keys import song_key  # noqa: E402

KEY_VERSION = 1
POLICY = "song-match-keys-backfill-v1"
NAMESPACE = uuid.UUID("3f1f6c2e-7a0e-4f38-9d0b-5b9f6f0c2d41")
AUTO = "existing_link"
LOCK_ID = 731064923

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query: str, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def derive(song_counts: Counter, unlinked: int) -> tuple[str, int | None, dict]:
    linked = {sid: n for sid, n in song_counts.items()}
    if len(linked) == 1 and not unlinked:
        sid = next(iter(linked))
        return "confirmed", sid, {"linked": linked[sid]}
    if len(linked) > 1:
        return "ambiguous", None, {"song_ids": {str(k): v for k, v in sorted(linked.items())}, "unlinked": unlinked}
    if linked:
        sid, n = next(iter(linked.items()))
        return "pending", None, {"candidate_song_id": sid, "linked": n, "unlinked": unlinked}
    return "pending", None, {}


def collect(conn) -> dict:
    """Compute the desired key rows. Read-only."""
    groups = rows(conn, """
        SELECT p.raw_title, p.raw_artist, p.song_id, count(*) AS n
        FROM performances p JOIN live_archives la ON la.id=p.archive_id AND la.archived_at IS NULL
        WHERE p.archived_at IS NULL GROUP BY p.raw_title, p.raw_artist, p.song_id
    """).fetchall()
    keys: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"n": 0, "songs": Counter(), "unlinked": 0, "spellings": Counter()})
    skipped = 0
    for g in groups:
        key = song_key(g["raw_title"], g["raw_artist"])
        if not key[0]:
            skipped += g["n"]
            continue
        entry = keys[key]
        entry["n"] += g["n"]
        entry["spellings"][(g["raw_title"], g["raw_artist"])] += g["n"]
        if g["song_id"] is None:
            entry["unlinked"] += g["n"]
        else:
            entry["songs"][g["song_id"]] += g["n"]
    desired = {}
    for key, entry in keys.items():
        status, song_id, evidence = derive(entry["songs"], entry["unlinked"])
        (title, artist), _ = entry["spellings"].most_common(1)[0]
        desired[key] = {"status": status, "song_id": song_id, "evidence": evidence, "count": entry["n"],
                        "sample_raw_title": title, "sample_raw_artist": artist,
                        "spellings": len(entry["spellings"])}
    # A dry-run may preview before revision 004 exists; there are no stored keys yet then.
    has_table = rows(conn, "SELECT to_regclass('public.song_match_keys') IS NOT NULL AS ok").fetchone()["ok"]
    existing = {(r["title_key"], r["artist_key"]): r for r in rows(conn,
        "SELECT * FROM song_match_keys WHERE key_version=%s", (KEY_VERSION,)).fetchall()} if has_table else {}
    return {"desired": desired, "existing": existing, "skipped_empty_title": skipped}


def plan(collected: dict) -> dict:
    desired, existing = collected["desired"], collected["existing"]
    inserts, updates = [], []
    for key, want in sorted(desired.items()):
        have = existing.get(key)
        row = {"title_key": key[0], "artist_key": key[1], **want}
        if have is None:
            inserts.append(row)
            continue
        auto = have["decided_by"] in (None, AUTO)  # never overwrite manual/provider decisions
        target = dict(occurrence_count=want["count"], sample_raw_title=want["sample_raw_title"],
                      sample_raw_artist=want["sample_raw_artist"])
        if auto:
            target.update(status=want["status"], song_id=want["song_id"], evidence=want["evidence"])
        current = {k: have[k] for k in target}
        if current != target:
            updates.append({"id": have["id"], "version": have["version"], "auto": auto, **target})
    gone = [r for key, r in existing.items() if key not in desired and r["occurrence_count"]]
    for r in gone:
        updates.append({"id": r["id"], "version": r["version"], "auto": False, "occurrence_count": 0,
                        "sample_raw_title": r["sample_raw_title"], "sample_raw_artist": r["sample_raw_artist"]})
    states = Counter(w["status"] for w in desired.values())
    counts = Counter()
    for w in desired.values():
        counts[w["status"]] += w["count"]
    return {"inserts": inserts, "updates": updates,
            "summary": {"keys": len(desired), "inserts": len(inserts), "updates": len(updates),
                        "keys_no_longer_seen": len(gone), "skipped_empty_title": collected["skipped_empty_title"],
                        "keys_by_status": dict(states), "performances_by_status": dict(counts),
                        "pending_with_candidate": sum(1 for w in desired.values() if "candidate_song_id" in w["evidence"])}}


def manifest_hash(result: dict) -> str:
    canonical = json.dumps({"policy": POLICY, "inserts": result["inserts"], "updates": result["updates"]},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def check_target(conn, *, require_004: bool = True) -> str:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    revisions = [r["version"] for r in rows(conn, "SELECT version FROM catalog_schema_migrations ORDER BY version")]
    if not identity or identity["schema_version"] != "catalog-v2" or (require_004 and "004" not in revisions):
        raise RuntimeError("Catalog must be catalog-v2 with revision 004 applied")
    return identity["id"]


def apply(conn, result: dict) -> dict:
    """Write the plan in the caller's transaction. Returns receipt status."""
    catalog_id = check_target(conn)
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    digest = manifest_hash(result)
    operation_id = uuid.uuid5(NAMESPACE, catalog_id + ":" + digest)
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    if not result["inserts"] and not result["updates"]:
        return {"status": "no_changes", "manifest_hash": digest}
    for row in result["inserts"]:
        decided = row["status"] != "pending"
        conn.execute("""INSERT INTO song_match_keys(key_version,title_key,artist_key,status,song_id,
                sample_raw_title,sample_raw_artist,occurrence_count,decided_by,decided_at,evidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN clock_timestamp() END,%s)""",
            (KEY_VERSION, row["title_key"], row["artist_key"], row["status"], row["song_id"],
             row["sample_raw_title"], row["sample_raw_artist"], row["count"],
             AUTO if decided else None, decided, Jsonb(row["evidence"])))
    for row in result["updates"]:
        if row["auto"]:
            decided = row["status"] != "pending"
            changed = conn.execute("""UPDATE song_match_keys SET occurrence_count=%s,sample_raw_title=%s,
                    sample_raw_artist=%s,status=%s,song_id=%s,evidence=%s,
                    decided_by=%s,decided_at=CASE WHEN %s THEN COALESCE(decided_at,clock_timestamp()) END
                WHERE id=%s AND version=%s AND (decided_by IS NULL OR decided_by=%s) RETURNING id""",
                (row["occurrence_count"], row["sample_raw_title"], row["sample_raw_artist"], row["status"],
                 row["song_id"], Jsonb(row["evidence"]), AUTO if decided else None, decided,
                 row["id"], row["version"], AUTO)).fetchone()
        else:
            changed = conn.execute("""UPDATE song_match_keys SET occurrence_count=%s,sample_raw_title=%s,
                    sample_raw_artist=%s WHERE id=%s AND version=%s RETURNING id""",
                (row["occurrence_count"], row["sample_raw_title"], row["sample_raw_artist"],
                 row["id"], row["version"])).fetchone()
        if not changed:
            raise RuntimeError("song_match_keys changed concurrently; rerun the dry-run")
    conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_summary)
        VALUES (%s,%s,%s,'batch_import',%s)""",
        (operation_id, catalog_id, digest, Jsonb({"kind": POLICY, **result["summary"]})))
    return {"status": "committed", "manifest_hash": digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write keys and a receipt in one transaction")
    args = parser.parse_args()
    try:
        uri = migrate_catalog.load_connection()
    except migrate_catalog.MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    with psycopg.connect(uri, connect_timeout=20, row_factory=dict_row) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not args.apply)
        check_target(conn, require_004=args.apply)
        result = plan(collect(conn))
        output = {"mode": "apply" if args.apply else "dry-run", **result["summary"]}
        if args.apply:
            output.update(apply(conn, result))
            conn.commit()
        else:
            conn.rollback()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
