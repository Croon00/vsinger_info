"""Fetch missing catalog video durations from YouTube, then audit and apply them.

--fetch saves API responses locally. --apply uses that saved snapshot; neither
mode overwrites an existing duration or writes a duration before a song start.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
import uuid

import httpx
import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from import_legacy_setlists import NAMESPACE, ROOT, connection_url, digest


SNAPSHOT = ROOT / "db-migration/reports/catalog-video-duration-youtube.json"
VERSION = "catalog-youtube-duration-v1"
API = "https://www.googleapis.com/youtube/v3/videos"


def duration_seconds(raw: str) -> int | None:
    match = re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", raw)
    if not match or not any(match.groups()):
        return None
    return sum(int(n or 0) * scale for n, scale in zip(match.groups(), (86400, 3600, 60, 1)))


def targets(conn):
    identity = conn.execute("SELECT id,schema_version FROM catalog_instance").fetchone()
    if not identity or identity[1] != "catalog-v1":
        raise ValueError("Unexpected catalog identity")
    rows = conn.execute("""SELECT v.id,v.platform_video_id,MAX(p.start_seconds)
        FROM videos v JOIN live_archives l ON l.video_id=v.id
        LEFT JOIN performances p ON p.archive_id=l.id AND p.archived_at IS NULL
        WHERE v.platform='youtube' AND v.duration_seconds IS NULL
          AND v.archived_at IS NULL AND l.archived_at IS NULL
        GROUP BY v.id,v.platform_video_id ORDER BY v.platform_video_id""").fetchall()
    return str(identity[0]), rows


async def fetch(rows, catalog_id):
    if not settings.youtube_api_key:
        raise ValueError("YOUTUBE_API_KEY is not configured")
    found = {}
    unavailable = []
    async with httpx.AsyncClient(timeout=30) as client:
        for start in range(0, len(rows), 50):
            batch = rows[start:start + 50]
            ids = [row[1] for row in batch]
            response = await client.get(API, params={"part": "contentDetails", "id": ",".join(ids),
                                                     "fields": "items(id,contentDetails/duration)",
                                                     "key": settings.youtube_api_key})
            if response.status_code != 200:
                raise RuntimeError(f"YouTube videos.list failed: HTTP {response.status_code}; completed {start} IDs")
            returned = {item["id"]: item for item in response.json().get("items", [])}
            if set(returned) - set(ids):
                raise ValueError("YouTube returned an unrequested video")
            for video_key in ids:
                item = returned.get(video_key)
                seconds = duration_seconds((item or {}).get("contentDetails", {}).get("duration", ""))
                if seconds is None:
                    unavailable.append(video_key)
                else:
                    found[video_key] = seconds
            print(json.dumps({"fetched": min(start + 50, len(rows)), "total": len(rows),
                              "available": len(found), "unavailable": len(unavailable)}), flush=True)
    snapshot = {"version": VERSION, "catalog_id": catalog_id,
                "requested_ids": [row[1] for row in rows], "durations": found,
                "unavailable": unavailable}
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snapshot


def apply_batch(conn, catalog_id: str, index: int, entries: list[dict]) -> tuple[str, int]:
    operation_id = uuid.uuid5(NAMESPACE, catalog_id + ":" + VERSION + ":" + str(index))
    manifest_hash = digest({"version": VERSION, "catalog_id": catalog_id, "index": index,
                            "entries": entries})
    with conn.transaction():
        conn.execute("SET LOCAL search_path=public")
        conn.execute("SET LOCAL statement_timeout='120s'")
        conn.execute("SET LOCAL lock_timeout='10s'")
        receipt = conn.execute("SELECT manifest_hash FROM catalog_imports WHERE operation_id=%s",
                               (operation_id,)).fetchone()
        if receipt:
            if receipt[0] != manifest_hash:
                raise ValueError("Duration receipt manifest changed")
            return "already_committed", 0
        before = conn.execute("""SELECT id,platform_video_id,duration_seconds,to_jsonb(videos)
            FROM videos WHERE id=ANY(%s) FOR UPDATE""", ([entry["id"] for entry in entries],)).fetchall()
        if len(before) != len(entries):
            raise ValueError("Target video disappeared")
        by_id = {item["id"]: item for item in entries}
        if any(key != by_id[video_id]["video_key"] or duration is not None
               for video_id, key, duration, _ in before):
            raise ValueError("Target duration or identity changed")
        changed = conn.execute("""UPDATE videos v SET duration_seconds=x.seconds
            FROM jsonb_to_recordset(%s::jsonb) x(id integer,seconds integer)
            WHERE v.id=x.id AND v.duration_seconds IS NULL
            RETURNING v.id,to_jsonb(v)""", (Jsonb(entries),)).fetchall()
        if len(changed) != len(entries):
            raise ValueError("Duration update count mismatch")
        old = {video_id: data for video_id, _, _, data in before}
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (operation_id, catalog_id, manifest_hash,
             Jsonb([{"entity_type": "videos", "video_id": by_id[video_id]["video_key"],
                     "new_id": video_id} for video_id, _ in changed]),
             Jsonb({"kind": VERSION, "updated": len(changed)}))).fetchone()[0]
        changes = [{"entity_id": video_id, "before_data": old[video_id], "after_data": after,
                    "provenance": {"source": "youtube_videos_list_contentDetails",
                                   "video_id": by_id[video_id]["video_key"]}}
                   for video_id, after in changed]
        conn.execute("""INSERT INTO catalog_changes
            (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
            SELECT %s,'videos',entity_id,'update',before_data,after_data,provenance
            FROM jsonb_to_recordset(%s::jsonb)
              x(entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
            (import_id, Jsonb(changes)))
    return "committed", len(changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.fetch and args.apply:
        parser.error("Run --fetch and --apply separately")
    with psycopg.connect(connection_url(), connect_timeout=10, autocommit=True,
                         prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            catalog_id, rows = targets(conn)
        print(json.dumps({"missing": len(rows), "planned_api_calls": (len(rows) + 49) // 50}), flush=True)
        if args.fetch:
            snapshot = asyncio.run(fetch(rows, catalog_id))
        else:
            if not SNAPSHOT.exists():
                raise ValueError("Fetch snapshot first with --fetch")
            snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if snapshot["version"] != VERSION or snapshot["catalog_id"] != catalog_id:
            raise ValueError("Snapshot belongs to another catalog")
        original_ids = set(snapshot["requested_ids"])
        if set(snapshot["durations"]) | set(snapshot["unavailable"]) != original_ids:
            raise ValueError("Incomplete snapshot")
        if args.apply:
            all_rows = conn.execute("""SELECT v.id,v.platform_video_id,v.duration_seconds,
                MAX(p.start_seconds) FROM videos v JOIN live_archives l ON l.video_id=v.id
                LEFT JOIN performances p ON p.archive_id=l.id AND p.archived_at IS NULL
                WHERE v.platform='youtube' AND v.platform_video_id=ANY(%s)
                GROUP BY v.id,v.platform_video_id,v.duration_seconds""",
                (list(original_ids),)).fetchall()
            current = {key: (video_id, existing, max_start)
                       for video_id, key, existing, max_start in all_rows}
            if set(current) != original_ids:
                raise ValueError("Snapshot target videos changed")
        else:
            current = {key: (video_id, None, max_start) for video_id, key, max_start in rows}
        safe, conflict = [], []
        for key, seconds in sorted(snapshot["durations"].items()):
            if key not in current:
                continue
            video_id, existing, max_start = current[key]
            if existing is not None and existing != seconds:
                raise ValueError("Existing duration differs from the YouTube snapshot")
            if seconds <= 0 or (max_start is not None and seconds < max_start):
                conflict.append({"video_id": key, "duration_seconds": seconds,
                                 "max_start_seconds": max_start})
            else:
                safe.append({"id": video_id, "video_key": key, "seconds": seconds})
        print(json.dumps({"available": len(snapshot["durations"]),
                          "unavailable": len(snapshot["unavailable"]),
                          "safe_remaining": len(safe), "duration_conflicts": len(conflict),
                          "conflict_examples": conflict[:20]}), flush=True)
        if not args.apply:
            return
        applied = 0
        for index in range(0, len(safe), 50):
            status, count = apply_batch(conn, catalog_id, index // 50, safe[index:index + 50])
            applied += count
            print(json.dumps({"batch": index // 50, "status": status,
                              "updated": count}), flush=True)
        print(json.dumps({"updated_total": applied, "unavailable": len(snapshot["unavailable"]),
                          "conflicts": conflict}), flush=True)


if __name__ == "__main__":
    main()
