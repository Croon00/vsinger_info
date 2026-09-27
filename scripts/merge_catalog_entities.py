"""Merge duplicate catalog artists and songs that are one entity stored twice.

Decision file: migrations/catalog/entity-merges-N.json
  {"policy": "catalog-entity-merge-v1",
   "artists": [{"source": 685, "target": 592, "reason": "..."}],
   "songs":   [{"source": 1370, "target": 1369, "reason": "..."}]}

Default is a READ ONLY dry-run that counts what would move. ``--apply`` writes ONE
transaction: every row referencing the source (found through the live foreign keys,
refused when an unknown one appears) is re-pointed to the target; a row that would
duplicate one the target already has (same song credit, same alias, ...) is deleted and
kept in the audit. Source names become target aliases, the source is archived, a song
merge is recorded in song_merges, and catalog_changes keeps the moved row ids and the
deleted rows under one catalog_imports receipt. Rerunning the same file is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import unicodedata
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POLICY = "catalog-entity-merge-v1"
NAMESPACE = uuid.UUID("0c6d1f3e-7a52-4b8e-9d14-6e2f8a3b5c71")
LOCK_ID = 731064923  # shared with the other song_match_keys writers

# (table, column, columns that together with the column are unique -- None: no uniqueness)
ARTIST_REFS = [
    ("song_artists", "artist_id", ["song_id"]),
    ("archive_artists", "artist_id", ["archive_id"]),
    ("performance_artists", "artist_id", ["performance_id"]),
    ("artist_external_accounts", "artist_id", ["account_id"]),
    ("album_artists", "artist_id", ["album_id"]),
    ("concert_artists", "artist_id", ["concert_id"]),
    ("cover_artists", "artist_id", ["cover_id"]),
    ("recording_artists", "artist_id", ["recording_id"]),
    ("artist_group_members", "member_id", ["group_id"]),
    ("artist_group_members", "group_id", ["member_id"]),
    ("artist_aliases", "artist_id", ["normalized_alias"]),
    ("live_archives", "primary_artist_id", None),
]
SONG_REFS = [
    ("performances", "song_id", None),
    ("song_match_keys", "song_id", None),
    ("recordings", "song_id", None),
    ("covers", "song_id", None),
    ("song_external_ids", "song_id", None),
    ("song_artists", "song_id", ["artist_id"]),
    ("song_aliases", "song_id", ["normalized_alias"]),
    ("karaoke_numbers", "song_id", ["provider", "number"]),
]

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def rows(conn, query, params=None):
    return conn.cursor(row_factory=dict_row).execute(query, params)


def alias_key(value: str) -> str:
    """normalized_alias as the admin schema generates it."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def ident(name: str) -> psycopg.sql.Identifier:
    return psycopg.sql.Identifier(name)


def check_foreign_keys(conn) -> None:
    """Refuse when a table references artists/songs that this script does not re-point."""
    live = {(r["tbl"], r["col"]) for r in rows(conn, """
        SELECT c.conrelid::regclass::text AS tbl, a.attname AS col FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
        WHERE c.contype='f' AND c.confrelid IN ('public.artists'::regclass,'public.songs'::regclass)
          AND c.conrelid::regclass::text <> 'song_merges'""")}
    known = {(t, c) for t, c, _ in ARTIST_REFS + SONG_REFS}
    if live - known:
        raise RuntimeError(f"Unknown references to artists/songs: {sorted(live - known)}; extend the merge script")


def check(conn, decisions: dict) -> str:
    identity = rows(conn, "SELECT id::text AS id, schema_version FROM catalog_instance").fetchone()
    revisions = [r["version"] for r in rows(conn, "SELECT version FROM catalog_schema_migrations ORDER BY version")]
    if identity["schema_version"] != "catalog-v2" or "004" not in revisions:
        raise RuntimeError("Catalog must be catalog-v2 with revision 004 applied")
    if decisions.get("policy") != POLICY:
        raise RuntimeError("Unexpected decision file policy")
    check_foreign_keys(conn)
    return identity["id"]


def verify(conn, decisions: dict, *, lock: bool) -> dict:
    """Both sides live, no chains, no pair twice. Returns the rows as they are now."""
    suffix = " FOR UPDATE" if lock else ""
    found = {}
    for kind, table in (("artists", "artists"), ("songs", "songs")):
        pairs = decisions.get(kind, [])
        ids = [x for p in pairs for x in (p["source"], p["target"])]
        if len(set(p["source"] for p in pairs)) != len(pairs):
            raise RuntimeError(f"{kind}: a source appears twice")
        if {p["source"] for p in pairs} & {p["target"] for p in pairs}:
            raise RuntimeError(f"{kind}: a source is also a target (merge chain)")
        current = {r["id"]: r for r in rows(conn, f"SELECT * FROM {table} WHERE id=ANY(%s)" + suffix, (ids,))}
        for p in pairs:
            for side in ("source", "target"):
                row = current.get(p[side])
                if row is None or row["archived_at"]:
                    raise RuntimeError(f"{kind} {p[side]} is missing or archived")
            if p["source"] == p["target"]:
                raise RuntimeError(f"{kind}: source equals target {p['source']}")
        found[kind] = current
    merged = {r[0] for r in conn.execute("SELECT source_song_id FROM song_merges WHERE source_song_id=ANY(%s)",
                                          ([p["source"] for p in decisions.get("songs", [])],))}
    if merged:
        raise RuntimeError(f"Songs already merged: {sorted(merged)}")
    return found


def move(conn, table: str, column: str, unique_with: list[str] | None, source: int, target: int, *, write: bool) -> dict:
    """Re-point one reference column; delete the source rows that would duplicate a target row."""
    t, c = ident(table), ident(column)
    sql = psycopg.sql
    duplicate = sql.SQL("FALSE")
    if unique_with:
        same = sql.SQL(" AND ").join(sql.SQL("o.{0} IS NOT DISTINCT FROM s.{0}").format(ident(u)) for u in unique_with)
        duplicate = sql.SQL("EXISTS (SELECT 1 FROM {t} o WHERE o.{c}=%(target)s AND {same})").format(t=t, c=c, same=same)
    params = {"source": source, "target": target}
    conflicts = rows(conn, sql.SQL("SELECT to_jsonb(s) AS row FROM {t} s WHERE s.{c}=%(source)s AND {dup} ORDER BY s.id")
                     .format(t=t, c=c, dup=duplicate), params).fetchall()
    if not write:
        total = conn.execute(sql.SQL("SELECT count(*) FROM {t} WHERE {c}=%(source)s").format(t=t, c=c), params).fetchone()[0]
        return {"moved": total - len(conflicts), "deleted": len(conflicts)}
    ids = [r["row"]["id"] for r in conflicts]
    if ids:
        conn.execute(sql.SQL("DELETE FROM {t} WHERE id=ANY(%s)").format(t=t), (ids,))
    moved = [r[0] for r in conn.execute(sql.SQL("UPDATE {t} SET {c}=%(target)s WHERE {c}=%(source)s RETURNING id")
                                        .format(t=t, c=c), params)]
    return {"moved": moved, "deleted": [r["row"] for r in conflicts]}


def merge_artist(conn, pair: dict, current: dict, *, write: bool) -> dict:
    source, target = current[pair["source"]], current[pair["target"]]
    result = {}
    for table, column, unique_with in ARTIST_REFS:
        result[f"{table}.{column}"] = move(conn, table, column, unique_with, source["id"], target["id"], write=write)
    taken = {alias_key(v) for v in (target["name_native"], target["name_ko"], target["name_latin"]) if v}
    taken |= {r[0] for r in conn.execute("SELECT normalized_alias FROM artist_aliases WHERE artist_id=%s", (target["id"],))}
    names = [v for v in dict.fromkeys((source["name_native"], source["name_ko"], source["name_latin"])) if v]
    new_aliases = [v for v in names if alias_key(v) not in taken]
    if write:
        for value in new_aliases:
            conn.execute("INSERT INTO artist_aliases(artist_id,alias,normalized_alias) VALUES (%s,%s,%s)",
                         (target["id"], value, alias_key(value)))
        if conn.execute("UPDATE artists SET archived_at=clock_timestamp() WHERE id=%s AND archived_at IS NULL",
                        (source["id"],)).rowcount != 1:
            raise RuntimeError(f"Artist {source['id']} changed during apply")
    result["aliases_added"] = new_aliases
    return result


def merge_song(conn, pair: dict, current: dict, *, write: bool) -> dict:
    source, target = current[pair["source"]], current[pair["target"]]
    result = {}
    base = conn.execute("SELECT coalesce(max(position), -1) FROM song_artists WHERE song_id=%s", (target["id"],)).fetchone()[0]
    for table, column, unique_with in SONG_REFS:
        result[f"{table}.{column}"] = move(conn, table, column, unique_with, source["id"], target["id"], write=write)
    if write and result["song_artists.song_id"]["moved"]:
        # Moved credits follow the target's own credits in display order.
        conn.execute("""UPDATE song_artists sa SET position=%s + x.n
            FROM (SELECT id, row_number() OVER (ORDER BY position, id) AS n FROM song_artists WHERE id=ANY(%s)) x
            WHERE sa.id=x.id""", (base, result["song_artists.song_id"]["moved"]))
    new_alias = None
    if alias_key(source["title_native"]) != alias_key(target["title_native"]):
        exists = conn.execute("SELECT 1 FROM song_aliases WHERE song_id=%s AND normalized_alias=%s",
                              (target["id"], alias_key(source["title_native"]))).fetchone()
        new_alias = None if exists else source["title_native"]
    if write:
        if new_alias:
            conn.execute("INSERT INTO song_aliases(song_id,alias,normalized_alias,source) VALUES (%s,%s,%s,'manual')",
                         (target["id"], new_alias, alias_key(new_alias)))
        if not target["title_latin"] and source["title_latin"]:
            conn.execute("UPDATE songs SET title_latin=%s WHERE id=%s", (source["title_latin"], target["id"]))
        if conn.execute("UPDATE songs SET archived_at=clock_timestamp() WHERE id=%s AND archived_at IS NULL",
                        (source["id"],)).rowcount != 1:
            raise RuntimeError(f"Song {source['id']} changed during apply")
    result["alias_added"] = new_alias
    return result


def manifest(decisions: dict) -> str:
    body = {k: decisions.get(k, []) for k in ("policy", "artists", "songs")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def summarize(results: dict) -> dict:
    def count(value):
        return value if isinstance(value, int) else len(value)
    out = {}
    for kind, pairs in results.items():
        for pair in pairs:
            label = f"{kind}:{pair['source']}->{pair['target']}"
            out[label] = {ref: {k: count(v) for k, v in moved.items()} for ref, moved in pair["refs"].items()
                          if isinstance(moved, dict) and any(count(v) for v in moved.values())}
            extra = pair["refs"].get("aliases_added") or pair["refs"].get("alias_added")
            if extra:
                out[label]["aliases_added"] = extra
    return out


def apply(conn, decisions: dict, *, write: bool) -> dict:
    catalog_id = check(conn, decisions)
    digest = manifest(decisions)
    operation_id = uuid.uuid5(NAMESPACE, catalog_id + ":" + digest)
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    if conn.execute("SELECT 1 FROM catalog_imports WHERE operation_id=%s", (operation_id,)).fetchone():
        return {"status": "already_committed", "manifest_hash": digest}
    current = verify(conn, decisions, lock=write)
    results = {"artists": [], "songs": []}
    for pair in decisions.get("artists", []):
        results["artists"].append({**pair, "refs": merge_artist(conn, pair, current["artists"], write=write)})
    for pair in decisions.get("songs", []):
        results["songs"].append({**pair, "refs": merge_song(conn, pair, current["songs"], write=write)})
    summary = summarize(results)
    if not write:
        return {"status": "would_commit", "manifest_hash": digest, "merges": summary}
    import_id = conn.execute("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,source_kind,
            result_mapping,result_summary) VALUES (%s,%s,%s,'merge',%s,%s) RETURNING id""",
        (operation_id, catalog_id, digest,
         Jsonb([{"entity_type": k, "source": p["source"], "target": p["target"]} for k in results for p in results[k]]),
         Jsonb({"kind": POLICY, "artists": len(results["artists"]), "songs": len(results["songs"])}))).fetchone()[0]
    for pair in results["songs"]:
        conn.execute("INSERT INTO song_merges(source_song_id,target_song_id,import_id,reason) VALUES (%s,%s,%s,%s)",
                     (pair["source"], pair["target"], import_id, pair["reason"]))
    changes = []
    for kind in ("artists", "songs"):
        entity = "artists" if kind == "artists" else "songs"
        for pair in results[kind]:
            changes.append({"entity_type": entity, "entity_id": pair["source"], "action": "merge",
                            "before_data": {"archived_at": None},
                            "after_data": {"merged_into": pair["target"], "archived": True},
                            "provenance": {"policy": POLICY, "reason": pair["reason"], "refs": pair["refs"]}})
    conn.execute("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
        SELECT %s,x.entity_type,x.entity_id,x.action,x.before_data,x.after_data,x.provenance
        FROM jsonb_to_recordset(%s::jsonb) x(entity_type text,entity_id integer,action text,before_data jsonb,
             after_data jsonb,provenance jsonb)""", (import_id, Jsonb(changes)))
    return {"status": "committed", "manifest_hash": digest, "import_id": import_id, "merges": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="Decision file, e.g. migrations/catalog/entity-merges-1.json")
    parser.add_argument("--apply", action="store_true", help="Write the merges in one transaction")
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
