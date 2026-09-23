"""Apply user-reviewed exceptional setlists from the versioned decision file.

Dry-run by default. ``--apply`` writes missing reviewed archives with receipts.
"""
from __future__ import annotations

import argparse
import json

import psycopg

from import_legacy_setlists import (
    EXPECTED_SHA256, ROOT, apply_bucket, connection_url, legacy_state,
    match_archive, remote_state,
)


DECISIONS = ROOT / "migrations/catalog/legacy-setlist-decisions.json"
REPORT = ROOT / "db-migration/reports/legacy-reviewed-setlists.json"


def reviewed_items(legacy: dict, target: dict, decisions: dict) -> list[tuple[str, dict]]:
    if decisions["source_dump_sha256"] != EXPECTED_SHA256:
        raise ValueError("Review decisions refer to a different source dump")
    archive_by_id = {int(row["id"]): row for row in legacy["archives"]}
    output = []
    for video_id, decision in decisions["decisions"].items():
        if decision["action"] == "exclude":
            continue
        if decision["action"] not in {"select_archive", "replace_setlist"}:
            raise ValueError("Unknown decision action")
        old_id = decision["legacy_archive_id"]
        row = archive_by_id[old_id]
        if row["youtube_video_id"] != video_id:
            raise ValueError("Reviewed archive/video mismatch")
        matched = match_archive(row, legacy, target)
        songs = legacy["performances"][old_id]
        if decision["action"] == "select_archive":
            if len(songs) != decision["expected_performances"]:
                raise ValueError("Reviewed setlist length changed")
            selected = [{"legacy_performance_id": int(song["id"]),
                         "ordinal": ordinal,
                         "start_seconds": int(song["start_seconds"]),
                         "raw_title": song["song_title"],
                         "raw_artist": song["original_artist"],
                         "raw_timestamp": song["timestamp_text"]}
                        for ordinal, song in enumerate(
                            sorted(songs, key=lambda song: (int(song["start_seconds"]), int(song["id"]))), 1)]
            batch_kind = "review-xf-10-v1"
        else:
            if video_id != "FHoFxjx8QGU" or old_id != 959:
                raise ValueError("Unrecognized curated setlist")
            if int(row["duration_seconds"]) != decision["verified_video_duration_seconds"]:
                raise ValueError("Verified duration differs from legacy row")
            group_id = target["by_slug"]["kmnz"]
            member_id = target["by_slug"]["kmnz-tina"]
            if (group_id, member_id) not in target["members"] or "#KMNZTINA" not in row["video_title"].upper():
                raise ValueError("KMNZ TINA title or membership evidence changed")
            if matched["primary_artist_id"] != group_id:
                raise ValueError("Legacy host was not the expected KMNZ group")
            matched["primary_artist_id"] = member_id
            matched["evidence"]["title_rule"] = "kmnz-tina"
            selected = []
            for ordinal, entry in enumerate(decision["performances"], 1):
                key = (entry["raw_title"], entry["raw_artist"])
                # Repeated titles retain their distinct legacy performance IDs by start time.
                candidates = [song for song in songs if
                              song["song_title"] == key[0] and song["original_artist"] == key[1]]
                exact = next((song for song in candidates if
                              int(song["start_seconds"]) == entry["start_seconds"]), None)
                original = exact or (candidates[0] if len(candidates) == 1 else None)
                if original is None:
                    raise ValueError("Curated performance cannot be traced to one legacy row")
                if entry["start_seconds"] > int(row["duration_seconds"]):
                    raise ValueError("Curated performance exceeds video duration")
                selected.append({"legacy_performance_id": int(original["id"]),
                                 "ordinal": ordinal, "start_seconds": entry["start_seconds"],
                                 "raw_title": entry["raw_title"], "raw_artist": entry["raw_artist"],
                                 "raw_timestamp": entry["raw_timestamp"]})
            if len({song["legacy_performance_id"] for song in selected}) != len(selected):
                raise ValueError("Curated rows map to overlapping legacy IDs")
            batch_kind = "review-fho-corrected-v1"
        item = {"legacy_archive_id": old_id, "video_id": video_id,
                "video_title": row["video_title"], "published_at": row["published_at"],
                "broadcast_at": row["broadcast_at"],
                "duration_seconds": int(row["duration_seconds"]) if row["duration_seconds"] else None,
                "top_comment": row["top_comment"], **matched, "performances": selected}
        if decision["action"] == "replace_setlist":
            item["curated_source_text"] = "User-reviewed setlist; song 6 corrected to 00:51:31.\n" + "\n".join(
                f'{song["ordinal"]:02d}. [{song["raw_timestamp"]}] {song["raw_title"]} / {song["raw_artist"]}'
                for song in selected)
        output.append((batch_kind, item))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    legacy = legacy_state()
    with psycopg.connect(connection_url(), connect_timeout=10, autocommit=True,
                         prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            target = remote_state(conn)
        items = reviewed_items(legacy, target, decisions)
        report = {"catalog_id": target["catalog_id"], "reviewed": [
            {"batch_kind": kind, "legacy_archive_id": item["legacy_archive_id"],
             "video_id": item["video_id"], "performance_count": len(item["performances"]),
             "primary_artist_id": item["primary_artist_id"]} for kind, item in items],
            "excluded": [key for key, decision in decisions["decisions"].items()
                         if decision["action"] == "exclude"]}
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        if args.apply:
            for kind, item in items:
                print(json.dumps({"video_id": item["video_id"], "result": apply_bucket(
                    conn, item["legacy_archive_id"] // 100, [item], target["catalog_id"], kind)}))


if __name__ == "__main__":
    main()
