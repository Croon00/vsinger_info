"""Review pending song_match_keys whose performances are already partly linked to one song.

``export`` (read-only) writes a decision file listing each such key with its candidate
song. A key whose normalized text equals the candidate's title and one of its original
artists' names is pre-filled ``confirm`` (basis ``exact``); every other key is left
``null`` for a person to decide. ``apply`` reads the file: dry-run by default, and
``--apply`` stores the decisions in one transaction with a receipt. It only changes
song_match_keys; linking performances is a separate step.

Allowed decisions: confirm, reject, not_song, ambiguous, or null (skip for now).
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.song_keys import normalize_text  # noqa: E402

DECISIONS = ROOT / "migrations" / "catalog" / "partial-match-key-decisions.json"
POLICY = "partial-match-key-review-v1"
NAMESPACE = uuid.UUID("8d3e2b71-4c55-4a0e-9f64-1e2d7c9b5a10")
LOCK_ID = 731064923  # shared with backfill_song_match_keys: never run both at once
STATUS = {"confirm": "confirmed", "reject": "rejected", "not_song": "not_song", "ambiguous": "ambiguous"}

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query: str, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def artist_names(conn, song_ids: list[int]) -> dict[int, set[str]]:
    names: dict[int, set[str]] = {sid: set() for sid in song_ids}
    for r in rows(conn, """
        SELECT sa.song_id, a.name_native, a.name_ko, a.name_latin,
               COALESCE(array_agg(al.alias) FILTER (WHERE al.alias IS NOT NULL), '{}') AS aliases
        FROM song_artists sa JOIN artists a ON a.id=sa.artist_id
        LEFT JOIN artist_aliases al ON al.artist_id=a.id
        WHERE sa.song_id=ANY(%s) GROUP BY sa.song_id, a.id""", (song_ids,)):
        for value in (r["name_native"], r["name_ko"], r["name_latin"], *r["aliases"]):
            if value:
                names[r["song_id"]].add(normalize_text(value))
    return names


def export(conn) -> dict:
    keys = rows(conn, """
        SELECT k.id, k.version, k.title_key, k.artist_key, k.sample_raw_title, k.sample_raw_artist,
               k.occurrence_count, k.evidence, s.id AS song_id, s.title_native, s.title_ko, s.archived_at
        FROM song_match_keys k JOIN songs s ON s.id=(k.evidence->>'candidate_song_id')::int
        WHERE k.status='pending' AND k.evidence ? 'candidate_song_id'
        ORDER BY (k.evidence->>'unlinked')::int DESC, k.id""").fetchall()
    names = artist_names(conn, sorted({k["song_id"] for k in keys}))
    display = {r["song_id"]: r["names"] for r in rows(conn, """
        SELECT sa.song_id, string_agg(a.name_native, ', ' ORDER BY sa.position, a.id) AS names
        FROM song_artists sa JOIN artists a ON a.id=sa.artist_id WHERE sa.song_id=ANY(%s) GROUP BY sa.song_id""",
        (sorted(names),))}
    entries = []
    for k in keys:
        title_ok = normalize_text(k["title_native"]) == k["title_key"]
        artist_ok = bool(k["artist_key"]) and k["artist_key"] in names[k["song_id"]]
        exact = title_ok and artist_ok and k["archived_at"] is None
        reasons = [] if exact else [r for r, bad in (
            ("title differs from candidate", not title_ok),
            ("no original artist in setlist text" if not k["artist_key"] else "artist differs from candidate", not artist_ok),
            ("candidate song archived", k["archived_at"] is not None)) if bad]
        suggested = "confirm" if exact else None
        entries.append({
            "key_id": k["id"], "key_version": k["version"], "title_key": k["title_key"], "artist_key": k["artist_key"],
            "raw_title": k["sample_raw_title"], "raw_artist": k["sample_raw_artist"],
            "linked": k["evidence"]["linked"], "unlinked": k["evidence"]["unlinked"],
            "candidate_song_id": k["song_id"], "candidate_title": k["title_native"],
            "candidate_title_ko": k["title_ko"], "candidate_artists": display.get(k["song_id"]),
            "basis": "exact" if exact else "needs_review", "review_notes": reasons,
            "suggested": suggested, "decision": suggested,
        })
    return {"policy": POLICY, "allowed_decisions": [*STATUS, None],
            "summary": {"keys": len(entries), "exact": sum(e["basis"] == "exact" for e in entries),
                        "needs_review": sum(e["basis"] != "exact" for e in entries)},
            "entries": entries}


def load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("policy") != POLICY:
        raise ValueError("Unexpected decision file policy")
    entries = data["entries"]
    for e in entries:
        if e["decision"] not in (*STATUS, None):
            raise ValueError(f"Invalid decision for key {e['key_id']}: {e['decision']!r}")
    return [e for e in entries if e["decision"] is not None]


def apply(conn, decided: list[dict], *, write: bool = True) -> dict:
    """Store decisions in the caller's transaction. Rejects stale or changed keys.

    With ``write=False`` it only checks, read-only, that every decision still matches.
    """
    identity = rows(conn, "SELECT id::text AS id FROM catalog_instance").fetchone()["id"]
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    payload = [{"id": e["key_id"], "version": e["key_version"], "status": STATUS[e["decision"]],
                "song_id": e["candidate_song_id"] if e["decision"] == "confirm" else None,
                "candidate": e["candidate_song_id"],
                # An untouched exact suggestion is rule-derived; anything else is a person's call.
                "decided_by": "existing_link" if e["basis"] == "exact" and e["decision"] == e["suggested"] else "manual"}
               for e in decided]
    digest = hashlib.sha256(json.dumps({"policy": POLICY, "decisions": payload}, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    operation_id = uuid.uuid5(NAMESPACE, identity + ":" + digest)
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    if not payload:
        return {"status": "no_decisions", "manifest_hash": digest}
    matching = """FROM jsonb_to_recordset(%s::jsonb) x(id integer,version integer,status text,song_id integer,
             candidate integer,decided_by text)
        JOIN songs s ON s.id=x.candidate AND s.archived_at IS NULL
        WHERE k.id=x.id AND k.version=x.version AND k.status='pending'
          AND (k.evidence->>'candidate_song_id')::int=x.candidate"""
    counts = {status: sum(p["status"] == status for p in payload) for status in STATUS.values()}
    rule_derived = sum(p["decided_by"] == "existing_link" for p in payload)
    if not write:
        matched = conn.execute("SELECT count(*) FROM song_match_keys k, " + matching.removeprefix("FROM "),
                               (Jsonb(payload),)).fetchone()[0]
        if matched != len(payload):
            raise RuntimeError("Some keys changed since export; re-export and review again")
        return {"status": "would_commit", "decisions": len(payload), **counts, "rule_derived": rule_derived}
    changed = conn.execute("""UPDATE song_match_keys k SET status=x.status, song_id=x.song_id,
            decided_by=x.decided_by, decided_at=clock_timestamp(),
            evidence=k.evidence || jsonb_build_object('review', %s::text)
        """ + matching, (POLICY, Jsonb(payload))).rowcount
    if changed != len(payload):
        raise RuntimeError("Some keys changed since export; re-export and review again")
    conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,result_summary)
        VALUES (%s,%s,%s,'manual',%s)""",
        (operation_id, identity, digest, Jsonb({"kind": POLICY, "decisions": len(payload), **counts,
                                                "rule_derived": rule_derived})))
    return {"status": "committed", "manifest_hash": digest, "decisions": len(payload), **counts,
            "rule_derived": rule_derived}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="Write the decision file (read-only DB access)")
    run = sub.add_parser("apply", help="Dry-run decisions; --apply stores them")
    run.add_argument("--apply", action="store_true")
    parser.add_argument("--file", type=Path, default=DECISIONS)
    args = parser.parse_args()
    uri = migrate_catalog.load_connection()
    writing = args.command == "apply" and args.apply
    with psycopg.connect(uri, connect_timeout=20) as conn:
        migrate_catalog.configure_transaction(conn, read_only=not writing)
        if args.command == "export":
            data = export(conn)
            conn.rollback()
            args.file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"file": str(args.file), **data["summary"]}, ensure_ascii=False))
            return 0
        decided = load(args.file)
        result = apply(conn, decided, write=writing)
        if writing:
            conn.commit()
        else:
            conn.rollback()
            result["mode"] = "dry-run"
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
