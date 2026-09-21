"""Explicit, resumable import of legacy YouTube setlists into catalog-v1.

Reads only the archived pg_dump and NEW_DATABASE_URL. The default is
an audit; --apply is required for writes. Never imports app.runtime or .env.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import uuid

import psycopg
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "db-migration/archive/legacy-neon/neonDB-2026-09-21.dump"
REPORT = ROOT / "db-migration/reports/legacy-setlist-import.json"
PG_RESTORE = Path(os.environ.get("POSTGRES_BIN", r"C:\Program Files\PostgreSQL\18\bin")) / "pg_restore.exe"
EXPECTED_SHA256 = "0a059e007616e99cfe02d1980ab70aeb8b755084e92dc020b448483ef0c56b27"
NAMESPACE = uuid.UUID("94a7c6c0-44c1-4d76-bf28-776674487c60")
BATCH_SIZE = 100  # Fixed legacy archive-ID buckets, independent of held rows.


def connection_url() -> str:
    spec = importlib.util.spec_from_file_location("catalog_migration", ROOT / "scripts/migrate_catalog.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.load_connection()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def unescape_copy(value: str) -> str | None:
    if value == r"\N":
        return None
    replacements = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    output = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 == len(value):
            output.append(char)
            index += 1
            continue
        next_char = value[index + 1]
        output.append(replacements.get(next_char, next_char))
        index += 2
    return "".join(output)


def dump_rows(table: str) -> list[dict]:
    if not re.fullmatch(r"[a-z_]+", table):
        raise ValueError("Invalid table name")
    command = [str(PG_RESTORE), "--data-only", "--table=" + table,
               "--file=-", str(DUMP)]
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="strict", check=True)
    lines = iter(result.stdout.splitlines())
    prefix = "COPY public." + table + " "
    header = next((line for line in lines if line.startswith(prefix)), None)
    if header is None:
        raise ValueError("Missing COPY data for " + table)
    columns = [column.strip() for column in header.split("(", 1)[1].split(")", 1)[0].split(",")]
    output = []
    for line in lines:
        if line == r"\.":
            return output
        values = line.split("\t")
        if len(values) != len(columns):
            raise ValueError("Invalid COPY row in " + table)
        output.append(dict(zip(columns, map(unescape_copy, values))))
    raise ValueError("Unterminated COPY data for " + table)


def normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def remote_state(conn) -> dict:
    identity = conn.execute("SELECT id,schema_version,initial_import_id FROM catalog_instance").fetchone()
    if not identity or identity[1] != "catalog-v1" or identity[2] is None:
        raise ValueError("Unexpected catalog identity or initial import state")
    artists = conn.execute("""SELECT id,slug,name_native,name_ko,name_latin,entity_kind,archived_at
                              FROM artists""").fetchall()
    aliases = conn.execute("SELECT artist_id,alias FROM artist_aliases").fetchall()
    accounts = conn.execute("SELECT id,platform,platform_id,archived_at FROM external_accounts").fetchall()
    links = conn.execute("SELECT account_id,artist_id,relationship FROM artist_external_accounts").fetchall()
    members = conn.execute("SELECT group_id,member_id FROM artist_group_members").fetchall()
    names = defaultdict(set)
    by_slug = {}
    by_id = {}
    for artist_id, slug, native, ko, latin, kind, archived_at in artists:
        if archived_at is not None:
            continue
        by_slug[slug] = artist_id
        by_id[artist_id] = {"slug": slug, "kind": kind, "name": native}
        for name in (native, ko, latin):
            if normalize(name):
                names[normalize(name)].add(artist_id)
    for artist_id, alias in aliases:
        if artist_id in by_id and normalize(alias):
            names[normalize(alias)].add(artist_id)
    by_platform = {}
    for account_id, platform, platform_id, archived_at in accounts:
        if archived_at is None and platform_id:
            by_platform[(platform, platform_id)] = account_id
    owners = defaultdict(set)
    for account_id, artist_id, relationship in links:
        if relationship == "owner" and artist_id in by_id:
            owners[account_id].add(artist_id)
    counts = {table: conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
              for table in ("videos", "live_archives", "performances")}
    return {"catalog_id": str(identity[0]), "names": names, "by_slug": by_slug,
            "by_id": by_id, "accounts": by_platform, "owners": owners,
            "members": set(members), "counts": counts}


def legacy_state() -> dict:
    if not DUMP.exists() or hashlib.sha256(DUMP.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Legacy dump missing or checksum changed")
    tables = {name: dump_rows(name) for name in (
        "artists", "artist_sources", "youtube_channel_monitors", "youtube_channel_videos",
        "youtube_live_archives", "youtube_song_performances")}
    sources = {int(row["id"]): row for row in tables["artist_sources"]}
    old_artists = {int(row["id"]): row for row in tables["artists"]}
    monitors = {int(row["id"]): row for row in tables["youtube_channel_monitors"]}
    by_archive = defaultdict(list)
    by_video = defaultdict(list)
    for row in tables["youtube_channel_videos"]:
        monitor = monitors.get(int(row["monitor_id"]))
        if monitor is None:
            continue
        if row["archive_id"] is not None:
            by_archive[int(row["archive_id"])].append(monitor)
        by_video[row["youtube_video_id"]].append(monitor)
    performances = defaultdict(list)
    for row in tables["youtube_song_performances"]:
        performances[int(row["archive_id"])].append(row)
    archive_groups = defaultdict(list)
    for row in tables["youtube_live_archives"]:
        archive_groups[row["youtube_video_id"]].append(row)
    return {"archives": tables["youtube_live_archives"], "performances": performances,
            "groups": archive_groups, "sources": sources, "old_artists": old_artists,
            "monitors_by_archive": by_archive, "monitors_by_video": by_video}


def related(state: dict, first: int, second: int) -> bool:
    return (first, second) in state["members"] or (second, first) in state["members"]


def match_archive(row: dict, legacy: dict, target: dict) -> dict:
    old_id = int(row["id"])
    video_id = row["youtube_video_id"]
    raw_performer = row["performer_name"]
    monitors = legacy["monitors_by_archive"].get(old_id) or legacy["monitors_by_video"].get(video_id, [])
    account_ids = {target["accounts"][("youtube", monitor["youtube_channel_id"])]
                   for monitor in monitors
                   if ("youtube", monitor["youtube_channel_id"]) in target["accounts"]}
    if len(account_ids) > 1:
        raise ValueError("multiple_youtube_accounts")
    source_account_id = next(iter(account_ids), None)
    channel_artists = set().union(*(target["owners"].get(aid, set()) for aid in account_ids))
    if len(channel_artists) > 1:
        raise ValueError("multiple_channel_owners")
    performer_artists = set(target["names"].get(normalize(raw_performer), set()))
    # The legacy collector stored a few Latin names with underscores.
    if not performer_artists and raw_performer:
        performer_artists = set(target["names"].get(normalize(raw_performer.replace("_", " ")), set()))
    # These tags are generated by the legacy KMNZ group-channel routing rule.
    if not performer_artists and raw_performer and raw_performer.upper().startswith("KMNZ "):
        member = raw_performer.split(" ", 1)[1].strip().lower()
        if member in {"lita", "tina", "nero"}:
            artist_id = target["by_slug"].get("kmnz-" + member)
            if artist_id:
                performer_artists = {artist_id}
    if len(performer_artists) > 1:
        raise ValueError("ambiguous_performer_name")
    source = legacy["sources"].get(int(row["source_id"])) if row["source_id"] else None
    x_artists = set()
    if source:
        account_id = target["accounts"].get(("x", source["external_user_id"]))
        if account_id:
            x_artists = set(target["owners"].get(account_id, set()))
        if not x_artists:
            old_artist = legacy["old_artists"].get(int(source["artist_id"]))
            if old_artist:
                x_artists = set(target["names"].get(normalize(old_artist["name"]), set()))
    if len(x_artists) > 1:
        raise ValueError("ambiguous_x_author")
    performer = next(iter(performer_artists), None)
    channel = next(iter(channel_artists), None)
    x_author = next(iter(x_artists), None)
    primary = performer or channel or x_author
    if primary is None:
        raise ValueError("unmatched_artist")
    if performer and channel and performer != channel and not related(target, performer, channel):
        raise ValueError("performer_channel_disagree")
    if x_author and x_author != primary and not related(target, x_author, primary):
        raise ValueError("x_author_disagrees")
    return {"source_account_id": source_account_id, "primary_artist_id": primary,
            "evidence": {"performer": performer, "channel_owner": channel, "x_author": x_author}}


def safe_duplicate_selections(legacy: dict) -> tuple[set[int], list[dict]]:
    """Choose a richest archive only when every other song list is its subset."""
    chosen = set()
    details = []
    for video_id, group in legacy["groups"].items():
        if len(group) < 2:
            continue
        populated = [row for row in group if legacy["performances"].get(int(row["id"]))]
        if not populated:
            continue

        def signature(row):
            return {(song["start_seconds"], song["song_title"],
                     song["original_artist"], song["timestamp_text"])
                    for song in legacy["performances"][int(row["id"])]}

        best = max(populated, key=lambda row: (len(signature(row)),
                    bool(row["top_comment"]), row["duration_seconds"] is not None,
                    row["broadcast_at"] is not None, -int(row["id"])))
        best_signature = signature(best)
        if not all(signature(row) <= best_signature for row in populated):
            continue
        # Distinct comments may be independent evidence. Keep such a group for review.
        comments = {row["top_comment"] for row in group if row["top_comment"]}
        if len(comments) > 1:
            continue
        chosen.add(int(best["id"]))
        details.append({"video_id": video_id, "selected_archive_id": int(best["id"]),
                        "collapsed_archive_ids": [int(row["id"]) for row in group
                                                  if int(row["id"]) != int(best["id"])],
                        "selected_performances": len(legacy["performances"][int(best["id"])])})
    return chosen, details


def build_plan(legacy: dict, target: dict,
               allowed_duplicate_ids: set[int] | None = None) -> tuple[list[dict], list[dict], dict]:
    allowed_duplicate_ids = allowed_duplicate_ids or set()
    ready = []
    held = []
    reasons = Counter()
    for row in sorted(legacy["archives"], key=lambda value: int(value["id"])):
        old_id = int(row["id"])
        songs = legacy["performances"].get(old_id, [])
        if not songs:
            continue
        reason = None
        if len(legacy["groups"][row["youtube_video_id"]]) > 1 and old_id not in allowed_duplicate_ids:
            reason = "duplicate_video_id"
        elif not re.fullmatch(r"[A-Za-z0-9_-]{11}", row["youtube_video_id"] or ""):
            reason = "invalid_video_id"
        elif not (row["video_title"] or "").strip():
            reason = "missing_video_title"
        elif any(not (song["song_title"] or "").strip() for song in songs):
            reason = "missing_song_title"
        elif any(int(song["start_seconds"]) < 0 for song in songs):
            reason = "negative_start_seconds"
        elif (row["duration_seconds"] is not None and
              any(int(song["start_seconds"]) > int(row["duration_seconds"]) for song in songs)):
            reason = "start_exceeds_video_duration"
        try:
            matched = match_archive(row, legacy, target) if reason is None else None
        except ValueError as error:
            reason = str(error)
            matched = None
        if reason:
            reasons[reason] += 1
            held.append({"legacy_archive_id": old_id, "video_id": row["youtube_video_id"],
                         "performance_count": len(songs), "reason": reason,
                         "performer_name": row["performer_name"]})
            continue
        ordered = sorted(songs, key=lambda song: (int(song["start_seconds"]), int(song["id"])))
        ready.append({"legacy_archive_id": old_id, "video_id": row["youtube_video_id"],
                      "video_title": row["video_title"], "published_at": row["published_at"],
                      "broadcast_at": row["broadcast_at"],
                      "duration_seconds": int(row["duration_seconds"]) if row["duration_seconds"] else None,
                      "top_comment": row["top_comment"], **matched,
                      "performances": [
                          {"legacy_performance_id": int(song["id"]), "ordinal": ordinal,
                           "start_seconds": int(song["start_seconds"]),
                           "raw_title": song["song_title"], "raw_artist": song["original_artist"],
                           "raw_timestamp": song["timestamp_text"]}
                          for ordinal, song in enumerate(ordered, 1)]})
    return ready, held, dict(reasons)


def insert_rows(conn, table: str, fields: str, types: str, rows: list[dict], returning: str):
    if not rows:
        return []
    query = f"""INSERT INTO {table} ({fields})
                SELECT {fields} FROM jsonb_to_recordset(%s::jsonb) AS x({types})
                RETURNING {returning},to_jsonb({table}) AS after_data"""
    return conn.execute(query, (Jsonb(rows),)).fetchall()


def apply_bucket(conn, bucket: int, items: list[dict], catalog_id: str,
                 batch_kind: str = "auto-v1") -> str:
    manifest = {"version": 1, "dump_sha256": EXPECTED_SHA256,
                "bucket": bucket, "items": items}
    if batch_kind != "auto-v1":
        manifest["batch_kind"] = batch_kind
    manifest_hash = digest(manifest)
    operation_id = uuid.uuid5(NAMESPACE, EXPECTED_SHA256 + ":" + batch_kind + ":" + str(bucket))
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL search_path = public")
        receipt = conn.execute("SELECT manifest_hash FROM catalog_imports WHERE operation_id=%s",
                               (operation_id,)).fetchone()
        if receipt:
            if receipt[0] != manifest_hash:
                raise ValueError("Existing receipt has a different manifest")
            return "already_committed"
        ids = [item["video_id"] for item in items]
        collision = conn.execute("SELECT platform_video_id FROM videos WHERE platform='youtube' AND platform_video_id=ANY(%s) LIMIT 1",
                                 (ids,)).fetchone()
        if collision:
            raise ValueError("Target video already exists; re-audit before retry")
        changes = []
        mapping = []
        counts = Counter()

        def record(table, result, old_id):
            entity_id, after_data = result[0], result[-1]
            changes.append({"entity_type": table, "entity_id": entity_id,
                            "after_data": after_data,
                            "provenance": {"legacy_id": old_id, "dump_sha256": EXPECTED_SHA256}})
            counts[table] += 1

        videos = insert_rows(conn, "videos", "platform,platform_video_id,source_account_id,title,published_at,duration_seconds,availability",
                             "platform text,platform_video_id text,source_account_id integer,title text,published_at timestamptz,duration_seconds integer,availability text",
                             [{"platform": "youtube", "platform_video_id": item["video_id"],
                               "source_account_id": item["source_account_id"],
                               "title": item["video_title"], "published_at": item["published_at"],
                               "duration_seconds": item["duration_seconds"], "availability": "unknown"}
                              for item in items], "id,platform_video_id")
        video_ids = {video_key: new_id for new_id, video_key, _ in videos}
        old_by_video = {item["video_id"]: item["legacy_archive_id"] for item in items}
        for result in videos:
            record("videos", result, old_by_video[result[1]])
        archives = insert_rows(conn, "live_archives", "video_id,primary_artist_id,broadcast_at,setlist_state",
                               "video_id integer,primary_artist_id integer,broadcast_at timestamptz,setlist_state text",
                               [{"video_id": video_ids[item["video_id"]],
                                 "primary_artist_id": item["primary_artist_id"],
                                 "broadcast_at": item["broadcast_at"], "setlist_state": "partial"}
                                for item in items], "id,video_id")
        old_by_video_id = {video_ids[item["video_id"]]: item["legacy_archive_id"] for item in items}
        archive_ids = {old_by_video_id[video_id]: new_id for new_id, video_id, _ in archives}
        for result in archives:
            old_id = old_by_video_id[result[1]]
            record("live_archives", result, old_id)
            mapping.append({"entity_type": "live_archives", "legacy_id": old_id, "new_id": result[0]})
            item = next(item for item in items if item["legacy_archive_id"] == old_id)
            for alias_id in item.get("collapsed_legacy_ids", []):
                mapping.append({"entity_type": "live_archives", "legacy_id": alias_id,
                                "new_id": result[0], "duplicate_of": old_id})
        hosts = insert_rows(conn, "archive_artists", "archive_id,artist_id,role,position",
                            "archive_id integer,artist_id integer,role text,position integer",
                            [{"archive_id": archive_ids[item["legacy_archive_id"]],
                              "artist_id": item["primary_artist_id"], "role": "host", "position": 0}
                             for item in items], "id,archive_id")
        old_by_archive_id = {new_id: old_id for old_id, new_id in archive_ids.items()}
        for result in hosts:
            record("archive_artists", result, old_by_archive_id[result[1]])
        docs_input = []
        for item in items:
            base_meta = {"legacy_archive_id": item["legacy_archive_id"],
                         "youtube_video_id": item["video_id"], "dump_sha256": EXPECTED_SHA256}
            if item["top_comment"] and item["top_comment"].strip():
                meta = {**base_meta, "evidence_type": "legacy_comment"}
                docs_input.append({"source_kind": "youtube_comment", "content_text": item["top_comment"],
                                   "content_hash": digest({"kind": "youtube_comment",
                                                           "text": item["top_comment"], "metadata": meta}),
                                   "source_metadata": meta})
            if item.get("curated_source_text"):
                meta = {**base_meta, "evidence_type": "user_corrected_setlist"}
                docs_input.append({"source_kind": "manual_note",
                                   "content_text": item["curated_source_text"],
                                   "content_hash": digest({"kind": "manual_note",
                                                           "text": item["curated_source_text"], "metadata": meta}),
                                   "source_metadata": meta})
        documents = insert_rows(conn, "source_documents", "source_kind,content_text,content_hash,source_metadata",
                                "source_kind text,content_text text,content_hash text,source_metadata jsonb",
                                docs_input, "id,source_metadata")
        document_ids = {}
        document_links = []
        for new_id, meta, _ in documents:
            old_id = int(meta["legacy_archive_id"])
            document_links.append({"archive_id": archive_ids[old_id],
                                   "document_id": new_id, "role": "setlist_evidence"})
            if meta["evidence_type"] == "user_corrected_setlist" or old_id not in document_ids:
                document_ids[old_id] = new_id
        for result in documents:
            record("source_documents", result, int(result[1]["legacy_archive_id"]))
        sources = insert_rows(conn, "archive_sources", "archive_id,document_id,role",
                              "archive_id integer,document_id integer,role text",
                              document_links,
                              "id,archive_id")
        for result in sources:
            record("archive_sources", result, old_by_archive_id[result[1]])
        performance_inputs = []
        old_by_position = {}
        for item in items:
            old_id = item["legacy_archive_id"]
            archive_id = archive_ids[old_id]
            for song in item["performances"]:
                old_by_position[(archive_id, song["ordinal"])] = song["legacy_performance_id"]
                performance_inputs.append({"archive_id": archive_id, "ordinal": song["ordinal"],
                                           "start_seconds": song["start_seconds"],
                                           "raw_title": song["raw_title"],
                                           "raw_artist": song["raw_artist"],
                                           "raw_timestamp": song["raw_timestamp"],
                                           "source_document_id": document_ids.get(old_id)})
        performances = insert_rows(conn, "performances",
                                   "archive_id,ordinal,start_seconds,raw_title,raw_artist,raw_timestamp,source_document_id",
                                   "archive_id integer,ordinal integer,start_seconds integer,raw_title text,raw_artist text,raw_timestamp text,source_document_id integer",
                                   performance_inputs, "id,archive_id,ordinal")
        for result in performances:
            legacy_id = old_by_position[(result[1], result[2])]
            record("performances", result, legacy_id)
            mapping.append({"entity_type": "performances", "legacy_id": legacy_id,
                            "new_id": result[0]})
        if len(performances) != len(performance_inputs):
            raise ValueError("Performance count mismatch")
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'batch_import',%s,%s) RETURNING id""",
            (operation_id, catalog_id, manifest_hash, Jsonb(mapping),
             Jsonb({"bucket": bucket, "counts": dict(counts), "dump_sha256": EXPECTED_SHA256}))).fetchone()[0]
        conn.execute("""INSERT INTO catalog_changes
            (import_id,entity_type,entity_id,action,after_data,provenance)
            SELECT %s,entity_type,entity_id,'create',after_data,provenance
            FROM jsonb_to_recordset(%s::jsonb)
              AS x(entity_type text,entity_id integer,after_data jsonb,provenance jsonb)""",
            (import_id, Jsonb(changes)))
    return "committed"


def repair_source_accounts(conn, bucket: int, items: list[dict], catalog_id: str) -> str:
    """Audited correction for videos written before source_account_id was included."""
    expected = {item["video_id"]: item["source_account_id"] for item in items
                if item["source_account_id"] is not None}
    if not expected:
        return "no_account_evidence"
    manifest_hash = digest({"version": 1, "kind": "source_account_correction",
                            "dump_sha256": EXPECTED_SHA256, "bucket": bucket, "expected": expected})
    operation_id = uuid.uuid5(NAMESPACE, EXPECTED_SHA256 + ":source-account-v1:" + str(bucket))
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL search_path = public")
        receipt = conn.execute("SELECT manifest_hash FROM catalog_imports WHERE operation_id=%s",
                               (operation_id,)).fetchone()
        if receipt:
            if receipt[0] != manifest_hash:
                raise ValueError("Source account correction receipt differs")
            return "already_corrected"
        previous = conn.execute("""SELECT id,platform_video_id,source_account_id,to_jsonb(videos)
            FROM videos WHERE platform='youtube' AND platform_video_id=ANY(%s) FOR UPDATE""",
            (list(expected),)).fetchall()
        if len(previous) != len(expected):
            raise ValueError("Expected videos are missing during source account repair")
        before = {video_key: (video_id, account_id, data)
                  for video_id, video_key, account_id, data in previous}
        for video_key, (_, account_id, _) in before.items():
            if account_id is not None and account_id != expected[video_key]:
                raise ValueError("Existing source account disagrees with the match")
        updates = [{"video_id": video_key, "account_id": account_id}
                   for video_key, account_id in expected.items()
                   if before[video_key][1] is None]
        if not updates:
            return "already_filled"
        changed = conn.execute("""UPDATE videos AS v SET source_account_id=x.account_id
            FROM jsonb_to_recordset(%s::jsonb) AS x(video_id text,account_id integer)
            WHERE v.platform='youtube' AND v.platform_video_id=x.video_id
              AND v.source_account_id IS NULL
            RETURNING v.id,v.platform_video_id,to_jsonb(v)""", (Jsonb(updates),)).fetchall()
        if len(changed) != len(updates):
            raise ValueError("Source account repair count mismatch")
        mapping = [{"entity_type": "videos", "video_id": key, "new_id": video_id}
                   for video_id, key, _ in changed]
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (operation_id, catalog_id, manifest_hash, Jsonb(mapping),
             Jsonb({"bucket": bucket, "source_accounts_corrected": len(changed),
                    "dump_sha256": EXPECTED_SHA256}))).fetchone()[0]
        changes = [{"entity_id": video_id, "before_data": before[key][2],
                    "after_data": data,
                    "provenance": {"video_id": key, "dump_sha256": EXPECTED_SHA256}}
                   for video_id, key, data in changed]
        conn.execute("""INSERT INTO catalog_changes
            (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
            SELECT %s,'videos',entity_id,'update',before_data,after_data,provenance
            FROM jsonb_to_recordset(%s::jsonb)
              AS x(entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
            (import_id, Jsonb(changes)))
    return "corrected"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write eligible batches to catalog")
    parser.add_argument("--apply-safe-duplicates", action="store_true",
                        help="Write duplicate-video groups whose song lists nest exactly")
    parser.add_argument("--bucket", type=int, help="Run only one fixed archive-ID bucket")
    args = parser.parse_args()
    legacy = legacy_state()
    with psycopg.connect(connection_url(), connect_timeout=10, autocommit=True,
                         prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            target = remote_state(conn)
        selected, duplicate_details = safe_duplicate_selections(legacy)
        ready, held, reasons = build_plan(legacy, target,
                                          selected if args.apply_safe_duplicates else set())
        if args.apply_safe_duplicates:
            ready = [item for item in ready if item["legacy_archive_id"] in selected]
            details_by_id = {detail["selected_archive_id"]: detail for detail in duplicate_details}
            for item in ready:
                item["collapsed_legacy_ids"] = details_by_id[item["legacy_archive_id"]]["collapsed_archive_ids"]
        by_bucket = defaultdict(list)
        for item in ready:
            by_bucket[item["legacy_archive_id"] // BATCH_SIZE].append(item)
        report = {"dump_sha256": EXPECTED_SHA256, "catalog_id": target["catalog_id"],
                  "target_counts_at_audit": target["counts"], "ready_archives": len(ready),
                  "ready_performances": sum(len(item["performances"]) for item in ready),
                  "held_archives": len(held), "held_performances": sum(item["performance_count"] for item in held),
                  "hold_reasons": reasons, "held": held,
                  "missing_source_account": sum(item["source_account_id"] is None for item in ready),
                  "buckets": sorted(by_bucket)}
        report_path = (REPORT.parent / "legacy-setlist-safe-duplicates.json"
                       if args.apply_safe_duplicates else REPORT)
        if args.apply_safe_duplicates:
            report["selected_duplicate_groups"] = duplicate_details
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key not in {"held", "buckets"}},
                         ensure_ascii=False))
        if not (args.apply or args.apply_safe_duplicates):
            return
        if target["counts"] != {"videos": 0, "live_archives": 0, "performances": 0}:
            # A resumed run may have our own receipts; apply_bucket checks each one.
            receipts = conn.execute("SELECT count(*) FROM catalog_imports WHERE result_summary->>'dump_sha256'=%s",
                                    (EXPECTED_SHA256,)).fetchone()[0]
            if receipts == 0:
                raise ValueError("Target contains video data without this import's receipts")
        for bucket in sorted(by_bucket):
            if args.bucket is not None and bucket != args.bucket:
                continue
            result = apply_bucket(conn, bucket, by_bucket[bucket], target["catalog_id"],
                                  "dedup-v1" if args.apply_safe_duplicates else "auto-v1")
            account_result = ("inserted_with_account" if args.apply_safe_duplicates else
                              repair_source_accounts(conn, bucket, by_bucket[bucket], target["catalog_id"]))
            print(json.dumps({"bucket": bucket, "result": result,
                              "source_accounts": account_result,
                              "archives": len(by_bucket[bucket]),
                              "performances": sum(len(i["performances"]) for i in by_bucket[bucket])}))


if __name__ == "__main__":
    main()
