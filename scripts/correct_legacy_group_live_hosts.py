"""Correct imported KMNZ/VESPERBELL group-host lives using legacy title tags.

Dry-run by default. --apply writes one audited correction transaction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid

import psycopg
from psycopg.types.json import Jsonb

from import_legacy_setlists import (EXPECTED_SHA256, NAMESPACE, ROOT, connection_url,
                                    digest, legacy_state)


REPORT = ROOT / "db-migration/reports/legacy-group-host-corrections.json"
OPERATION_ID = uuid.uuid5(NAMESPACE, EXPECTED_SHA256 + ":group-host-title-v1")


def desired_slug(archive: dict) -> str | None:
    title = archive["video_title"] or ""
    performer = archive["performer_name"] or ""
    if performer.casefold() == "kmnz":
        upper = title.upper()
        for member in ("lita", "nero", "tina"):
            if "#KMNZ" + member.upper() in upper:
                return "kmnz-" + member
    if performer.casefold() == "vesperbell":
        if "ヨミ" in title:
            return "vesperbell-yomi"
        if "カスカ" in title:
            return "vesperbell-kasuka"
    return None


def collect_candidates(conn, legacy: dict) -> list[dict]:
    old_by_id = {int(row["id"]): row for row in legacy["archives"]}
    artists = {slug: (artist_id, kind) for artist_id, slug, kind in conn.execute(
        "SELECT id,slug,entity_kind FROM artists WHERE archived_at IS NULL")}
    memberships = set(conn.execute("SELECT group_id,member_id FROM artist_group_members").fetchall())
    rows = conn.execute("""SELECT DISTINCT ON (l.id)
        l.id,l.primary_artist_id,aa.id,aa.artist_id,aa.role,v.platform_video_id,
        (sd.source_metadata->>'legacy_archive_id')::integer
        FROM live_archives l JOIN videos v ON v.id=l.video_id
        JOIN archive_artists aa ON aa.archive_id=l.id
        JOIN archive_sources ars ON ars.archive_id=l.id
        JOIN source_documents sd ON sd.id=ars.document_id
        WHERE sd.source_metadata ? 'legacy_archive_id'
        ORDER BY l.id,sd.id""").fetchall()
    candidates = []
    for archive_id, primary_id, link_id, linked_id, role, video_id, old_id in rows:
        source = old_by_id.get(old_id)
        if not source or source["youtube_video_id"] != video_id:
            raise ValueError("Legacy provenance does not match the imported video")
        desired = desired_slug(source)
        if not desired:
            continue
        group_slug = desired.split("-", 1)[0]
        if group_slug == "vesperbell":
            group_slug = "vesperbell"
        group_id, group_kind = artists[group_slug]
        member_id, member_kind = artists[desired]
        if group_kind != "group" or member_kind != "solo" or (group_id, member_id) not in memberships:
            raise ValueError("Missing catalog group-member relationship")
        if primary_id == member_id and linked_id == member_id:
            continue
        if primary_id != group_id or linked_id != group_id or role != "host":
            raise ValueError("Imported host differs from the expected group")
        candidates.append({"legacy_archive_id": old_id, "video_id": video_id,
                           "archive_id": archive_id, "archive_artist_id": link_id,
                           "from_artist_id": group_id, "to_artist_id": member_id,
                           "title_rule": desired})
    return sorted(candidates, key=lambda item: item["archive_id"])


def apply(conn, candidates: list[dict], catalog_id: str) -> str:
    manifest_hash = digest({"version": 1, "kind": "group_host_title_correction",
                            "dump_sha256": EXPECTED_SHA256, "candidates": candidates})
    with conn.transaction():
        conn.execute("SET LOCAL search_path = public")
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("SET LOCAL lock_timeout = '10s'")
        receipt = conn.execute("SELECT manifest_hash FROM catalog_imports WHERE operation_id=%s",
                               (OPERATION_ID,)).fetchone()
        if receipt:
            return "already_corrected"
        if not candidates:
            return "nothing_to_correct"
        ids = [item["archive_id"] for item in candidates]
        links = [item["archive_artist_id"] for item in candidates]
        old_archives = {archive_id: data for archive_id, data in conn.execute(
            "SELECT id,to_jsonb(live_archives) FROM live_archives WHERE id=ANY(%s) FOR UPDATE",
            (ids,)).fetchall()}
        old_links = {link_id: data for link_id, data in conn.execute(
            "SELECT id,to_jsonb(archive_artists) FROM archive_artists WHERE id=ANY(%s) FOR UPDATE",
            (links,)).fetchall()}
        if len(old_archives) != len(candidates) or len(old_links) != len(candidates):
            raise ValueError("Some host rows changed before correction")
        for item in candidates:
            if (old_archives[item["archive_id"]]["primary_artist_id"] != item["from_artist_id"]
                    or old_links[item["archive_artist_id"]]["artist_id"] != item["from_artist_id"]):
                raise ValueError("Host changed before correction")
        changed_archives = conn.execute("""UPDATE live_archives AS l SET primary_artist_id=x.to_artist_id
            FROM jsonb_to_recordset(%s::jsonb)
              AS x(archive_id integer,from_artist_id integer,to_artist_id integer)
            WHERE l.id=x.archive_id AND l.primary_artist_id=x.from_artist_id
            RETURNING l.id,to_jsonb(l)""", (Jsonb(candidates),)).fetchall()
        changed_links = conn.execute("""UPDATE archive_artists AS a SET artist_id=x.to_artist_id
            FROM jsonb_to_recordset(%s::jsonb)
              AS x(archive_artist_id integer,from_artist_id integer,to_artist_id integer)
            WHERE a.id=x.archive_artist_id AND a.artist_id=x.from_artist_id
            RETURNING a.id,to_jsonb(a)""", (Jsonb(candidates),)).fetchall()
        if len(changed_archives) != len(candidates) or len(changed_links) != len(candidates):
            raise ValueError("Host correction count mismatch")
        by_archive = {item["archive_id"]: item for item in candidates}
        by_link = {item["archive_artist_id"]: item for item in candidates}
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
            (OPERATION_ID, catalog_id, manifest_hash, Jsonb(candidates),
             Jsonb({"group_host_corrections": len(candidates), "dump_sha256": EXPECTED_SHA256}))).fetchone()[0]
        changes = []
        for archive_id, after_data in changed_archives:
            item = by_archive[archive_id]
            changes.append({"entity_type": "live_archives", "entity_id": archive_id,
                            "before_data": old_archives[archive_id], "after_data": after_data,
                            "provenance": {"legacy_archive_id": item["legacy_archive_id"],
                                           "title_rule": item["title_rule"]}})
        for link_id, after_data in changed_links:
            item = by_link[link_id]
            changes.append({"entity_type": "archive_artists", "entity_id": link_id,
                            "before_data": old_links[link_id], "after_data": after_data,
                            "provenance": {"legacy_archive_id": item["legacy_archive_id"],
                                           "title_rule": item["title_rule"]}})
        conn.execute("""INSERT INTO catalog_changes
            (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
            SELECT %s,entity_type,entity_id,'update',before_data,after_data,provenance
            FROM jsonb_to_recordset(%s::jsonb)
              AS x(entity_type text,entity_id integer,before_data jsonb,after_data jsonb,provenance jsonb)""",
            (import_id, Jsonb(changes)))
        invalid = conn.execute("""SELECT count(*) FROM live_archives l
            WHERE l.id=ANY(%s) AND NOT EXISTS (
              SELECT 1 FROM archive_artists a WHERE a.archive_id=l.id
                AND a.artist_id=l.primary_artist_id)""", (ids,)).fetchone()[0]
        if invalid:
            raise ValueError("Corrected primary artist lacks an archive link")
    return "corrected"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    legacy = legacy_state()
    with psycopg.connect(connection_url(), autocommit=True, prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            catalog_id = str(conn.execute("SELECT id FROM catalog_instance").fetchone()[0])
            candidates = collect_candidates(conn, legacy)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"catalog_id": catalog_id,
                                      "candidate_count": len(candidates),
                                      "candidates": candidates}, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(json.dumps({"candidate_count": len(candidates)}))
        if args.apply:
            print(json.dumps({"result": apply(conn, candidates, catalog_id)}))


if __name__ == "__main__":
    main()
