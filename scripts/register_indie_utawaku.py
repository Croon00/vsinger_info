"""Register the three reviewed independent singers and queue five recent song streams each.

Dry-run by default. --apply writes artists, YouTube owner links, and bounded backfill
jobs in one transaction. No concerts, calendar entries, or Discord routes are created.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.schemas.worker_jobs import JobRequest
from scripts.migrate_catalog import configure_transaction, load_connection

SEED = ROOT / "data/seeds/indie_utawaku_2026-10-02.json"
POLICY = "indie-utawaku-2026-10-02-v1"
NAMESPACE = uuid.UUID("55a7b968-c120-4d74-964b-3a46479618a8")


def register(conn, items: list[dict], *, write: bool) -> dict:
    identity = conn.execute("SELECT id::text,schema_version FROM catalog_instance").fetchone()
    revisions = [row[0] for row in conn.execute("SELECT version FROM catalog_schema_migrations ORDER BY version")]
    if not identity or identity[1] != "catalog-v2" or revisions != [f"{n:03}" for n in range(1, 7)]:
        raise RuntimeError("Unexpected unified catalog identity or revision")
    if write:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (731064923,))
    changes, mappings, plans = [], [], []
    for item in items:
        if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", item["channel_id"]):
            raise ValueError("Invalid channel ID")
        if len(item["backfill_video_ids"]) != 5 or len(set(item["backfill_video_ids"])) != 5:
            raise ValueError("Expected five unique video IDs per channel")
        artist = conn.execute("SELECT id,name_native,archived_at FROM artists WHERE slug=%s", (item["slug"],)).fetchone()
        account = conn.execute("""SELECT id,platform_id,archived_at,collection_enabled
            FROM external_accounts WHERE platform='youtube' AND platform_id=%s""",
            (item["channel_id"],)).fetchone()
        by_url = conn.execute("SELECT id FROM external_accounts WHERE platform='youtube' AND url=%s",
                              (item["channel_url"],)).fetchone()
        by_name = conn.execute("SELECT id FROM artists WHERE lower(name_native)=lower(%s) AND archived_at IS NULL",
                               (item["name_native"],)).fetchall()
        if (artist and (artist[1] != item["name_native"] or artist[2])) or (account and account[2]):
            raise RuntimeError(f"Archived or conflicting identity: {item['slug']}")
        if by_url and (not account or by_url[0] != account[0]):
            raise RuntimeError(f"YouTube URL belongs to another account: {item['slug']}")
        if by_name and (not artist or any(row[0] != artist[0] for row in by_name)):
            raise RuntimeError(f"Artist name already registered under another slug: {item['slug']}")
        if artist and account:
            link = conn.execute("""SELECT id FROM artist_external_accounts
                WHERE artist_id=%s AND account_id=%s AND relationship='owner'""",
                (artist[0], account[0])).fetchone()
            if not link or not account[3]:
                raise RuntimeError(f"Partial registration requires review: {item['slug']}")
        elif artist or account:
            raise RuntimeError(f"Partial registration requires review: {item['slug']}")
        plans.append({"slug": item["slug"], "action": "already_registered" if artist else "create",
                      "backfill_video_ids": item["backfill_video_ids"]})
    if not write:
        return {"status": "dry_run", "plans": plans}

    for item, plan in zip(items, plans):
        if plan["action"] == "already_registered":
            continue
        artist_id, artist_after = conn.execute("""INSERT INTO artists
            (slug,name_native,name_ko,name_latin,entity_kind,is_virtual,show_in_catalog)
            VALUES (%s,%s,%s,%s,'solo',true,true) RETURNING id,to_jsonb(artists)""",
            (item["slug"], item["name_native"], item["name_ko"], item["name_latin"])).fetchone()
        account_id, account_after = conn.execute("""INSERT INTO external_accounts
            (platform,platform_id,handle,url,collection_enabled)
            VALUES ('youtube',%s,%s,%s,true) RETURNING id,to_jsonb(external_accounts)""",
            (item["channel_id"], item["handle"], item["channel_url"])).fetchone()
        link_id, link_after = conn.execute("""INSERT INTO artist_external_accounts
            (artist_id,account_id,relationship,is_primary,position)
            VALUES (%s,%s,'owner',true,0) RETURNING id,to_jsonb(artist_external_accounts)""",
            (artist_id, account_id)).fetchone()
        for entity_type, key, after in (("artists", artist_id, artist_after),
                                        ("external_accounts", account_id, account_after),
                                        ("artist_external_accounts", link_id, link_after)):
            changes.append((entity_type, key, after, {"policy": POLICY, "source_url": item["channel_url"]}))
            mappings.append({"entity_type": entity_type, "id": key, "slug": item["slug"]})
        plan.update(artist_id=artist_id, account_id=account_id)
        request = JobRequest(job_type="youtube_poll", external_account_id=account_id,
                             payload={"channel_id": item["channel_id"],
                                      "request_run": "indie-utawaku-2026-10-02",
                                      "backfill_video_ids": item["backfill_video_ids"]})
        job_id = conn.execute("""INSERT INTO worker_jobs
            (job_type,idempotency_key,external_account_id,payload,max_attempts)
            VALUES ('youtube_poll',%s,%s,%s,5) RETURNING id""",
            (request.key(), account_id, Jsonb(request.parsed_payload().model_dump()))).fetchone()[0]
        plan["backfill_job_id"] = job_id
    if changes:
        body = {"policy": POLICY, "items": items}
        digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
        operation_id = uuid.uuid5(NAMESPACE, identity[0] + ":" + digest)
        import_id = conn.execute("""INSERT INTO catalog_imports
            (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
            VALUES (%s,%s,%s,'manual',%s,%s) RETURNING id""",
            (operation_id, identity[0], digest, Jsonb(mappings),
             Jsonb({"kind": POLICY, "artists": len(items), "backfill_jobs": len(items)}))).fetchone()[0]
        for entity_type, key, after, provenance in changes:
            conn.execute("""INSERT INTO catalog_changes
                (import_id,entity_type,entity_id,action,after_data,provenance)
                VALUES (%s,%s,%s,'create',%s,%s)""",
                (import_id, entity_type, key, Jsonb(after), Jsonb(provenance)))
    return {"status": "committed" if changes else "already_registered", "plans": plans}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    items = json.loads(SEED.read_text(encoding="utf-8"))
    with psycopg.connect(load_connection(), connect_timeout=20) as conn:
        configure_transaction(conn, read_only=not args.apply)
        result = register(conn, items, write=args.apply)
        if not args.apply:
            conn.rollback()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
