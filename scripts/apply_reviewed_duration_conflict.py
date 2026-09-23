"""Apply the user's timestamp correction and YouTube duration in one transaction."""
from __future__ import annotations

import argparse
import json
import uuid

import psycopg
from psycopg.types.json import Jsonb

from import_legacy_setlists import NAMESPACE, ROOT, connection_url, digest


DECISION = ROOT / "migrations/catalog/duration-conflict-decisions.json"
SNAPSHOT = ROOT / "db-migration/reports/catalog-video-duration-youtube.json"
VERSION = "reviewed-duration-conflict-v1"


def apply(conn, decision: dict, catalog_id: str) -> str:
    operation_id = uuid.uuid5(NAMESPACE, catalog_id + ":" + VERSION + ":" + decision["video_id"])
    manifest_hash = digest({"version": VERSION, "catalog_id": catalog_id, "decision": decision})
    with conn.transaction():
        conn.execute("SET LOCAL search_path=public")
        conn.execute("SET LOCAL lock_timeout='10s'")
        receipt = conn.execute("SELECT manifest_hash FROM catalog_imports WHERE operation_id=%s",
                               (operation_id,)).fetchone()
        if receipt:
            if receipt[0] != manifest_hash:
                raise ValueError("Reviewed decision receipt differs")
            return "already_committed"
        row = conn.execute("""SELECT v.id,to_jsonb(v),p.id,to_jsonb(p)
            FROM videos v JOIN live_archives l ON l.video_id=v.id
            JOIN performances p ON p.archive_id=l.id
            WHERE v.platform='youtube' AND v.platform_video_id=%s AND p.ordinal=%s
            FOR UPDATE OF v,p""",
            (decision["video_id"], decision["performance_ordinal"])).fetchone()
        if row is None:
            raise ValueError("Reviewed video/performance not found")
        video_id, old_video, performance_id, old_performance = row
        if (old_video["duration_seconds"] is not None or
                old_performance["raw_title"] != decision["raw_title"] or
                old_performance["start_seconds"] != decision["old_start_seconds"] or
                old_performance["raw_timestamp"] != decision["old_raw_timestamp"] or
                decision["corrected_start_seconds"] > decision["youtube_duration_seconds"]):
            raise ValueError("Reviewed preconditions no longer match")
        updated_performance = conn.execute("""UPDATE performances SET
            start_seconds=%s,raw_timestamp=%s WHERE id=%s RETURNING to_jsonb(performances)""",
            (decision["corrected_start_seconds"], decision["corrected_raw_timestamp"],
             performance_id)).fetchone()[0]
        updated_video = conn.execute("""UPDATE videos SET duration_seconds=%s
            WHERE id=%s RETURNING to_jsonb(videos)""",
            (decision["youtube_duration_seconds"], video_id)).fetchone()[0]
        invalid = conn.execute("""SELECT count(*) FROM performances p
            JOIN live_archives l ON l.id=p.archive_id WHERE l.video_id=%s
              AND p.start_seconds>%s""",
            (video_id, decision["youtube_duration_seconds"])).fetchone()[0]
        if invalid:
            raise ValueError("Another song is outside the verified duration")
        mapping = [{"entity_type": "performances", "new_id": performance_id},
                   {"entity_type": "videos", "new_id": video_id}]
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (operation_id, catalog_id, manifest_hash, Jsonb(mapping),
             Jsonb({"kind": VERSION, "decision": decision["decision"]}))).fetchone()[0]
        changes = [
            {"entity_type": "performances", "entity_id": performance_id,
             "before_data": old_performance, "after_data": updated_performance},
            {"entity_type": "videos", "entity_id": video_id,
             "before_data": old_video, "after_data": updated_video},
        ]
        conn.execute("""INSERT INTO catalog_changes
            (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
            SELECT %s,entity_type,entity_id,'update',before_data,after_data,%s::jsonb
            FROM jsonb_to_recordset(%s::jsonb)
              x(entity_type text,entity_id integer,before_data jsonb,after_data jsonb)""",
            (import_id, Jsonb({"policy": VERSION, "video_id": decision["video_id"],
                               "source": "user_timestamp_correction_and_youtube_contentDetails"}),
             Jsonb(changes)))
    return "committed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot["durations"].get(decision["video_id"]) != decision["youtube_duration_seconds"]:
        raise ValueError("YouTube snapshot differs from the reviewed duration")
    with psycopg.connect(connection_url(), connect_timeout=10, autocommit=True,
                         prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            catalog_id = str(conn.execute("SELECT id FROM catalog_instance").fetchone()[0])
        print(json.dumps({"video_id": decision["video_id"],
                          "corrected_start_seconds": decision["corrected_start_seconds"],
                          "duration_seconds": decision["youtube_duration_seconds"]}))
        if args.apply:
            print(json.dumps({"result": apply(conn, decision, catalog_id)}))


if __name__ == "__main__":
    main()
