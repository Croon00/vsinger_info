"""Read-only comparison of source-dump video durations and migrated values."""
from __future__ import annotations

from collections import Counter
import json

import psycopg

from import_legacy_setlists import connection_url, legacy_state


def main() -> None:
    legacy = legacy_state()
    old = {int(row["id"]): row for row in legacy["archives"]}
    with psycopg.connect(connection_url(), connect_timeout=10) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute("""SELECT v.platform_video_id,v.duration_seconds,
            (d.source_metadata->>'legacy_archive_id')::integer
            FROM videos v JOIN live_archives l ON l.video_id=v.id
            JOIN archive_sources s ON s.archive_id=l.id
            JOIN source_documents d ON d.id=s.document_id
            WHERE v.platform='youtube' AND d.source_metadata ? 'legacy_archive_id'
            ORDER BY v.id,d.id""").fetchall()
    seen = {}
    for video_key, target_duration, old_id in rows:
        if video_key in seen:
            if seen[video_key][1] != old_id:
                raise ValueError("Multiple source archive IDs for one migrated video")
            continue
        if old_id not in old or old[old_id]["youtube_video_id"] != video_key:
            raise ValueError("Source provenance mismatch")
        source = old[old_id]["duration_seconds"]
        seen[video_key] = (target_duration, old_id, int(source) if source is not None else None)
    counts = Counter()
    mismatches = []
    alternate = []
    for video_key, (target_duration, old_id, source_duration) in seen.items():
        if target_duration is None:
            counts["target_null"] += 1
            if source_duration is None:
                counts["both_null"] += 1
                other = sorted({int(row["duration_seconds"])
                                for row in legacy["groups"][video_key]
                                if row["duration_seconds"] is not None})
                if other:
                    alternate.append({"video_id": video_key, "selected_archive_id": old_id,
                                      "other_source_durations": other})
            else:
                counts["lost_during_import"] += 1
                mismatches.append({"video_id": video_key, "old_id": old_id,
                                   "source": source_duration, "target": None})
        else:
            counts["target_nonnull"] += 1
            if source_duration is None:
                counts["target_filled_without_source"] += 1
            elif target_duration != source_duration:
                counts["different_value"] += 1
                mismatches.append({"video_id": video_key, "old_id": old_id,
                                   "source": source_duration, "target": target_duration})
            else:
                counts["same_nonnull"] += 1
    print(json.dumps({"compared": len(seen), "counts": counts,
                      "alternate_duration_in_duplicate_source": alternate,
                      "mismatches": mismatches[:20]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
