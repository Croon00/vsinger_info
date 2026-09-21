"""Prepare and apply the reviewed legacy runtime subset to the unified DB.

The default is a read-only dry-run. ``--apply`` additionally requires the exact
dry-run manifest and is reserved for the phase-5 cutover.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

try:
    from scripts import audit_single_db_readiness as audit
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    import audit_single_db_readiness as audit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "db-migration" / "reports" / "single-db-readiness"
    / "runtime-migration-manifest.json"
)
NAMESPACE = uuid.UUID("f5a9e298-502c-4d44-aea2-ab27d276370c")
EXPECTED_REVISIONS = ("001", "002")
LOCK_ID = 731064922


class RuntimeMigrationError(RuntimeError):
    pass


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=json_default,
    ).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def json_ready(value):
    return json.loads(canonical(value).decode("utf-8"))


def configured_url(variable: str, filename: str) -> str:
    value = (dotenv_values(ROOT / filename).get(variable) or "").strip()
    if not value:
        raise RuntimeMigrationError(f"{variable} is not configured in {filename}")
    return value


def configure(conn, *, read_only: bool) -> None:
    if read_only:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    else:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    conn.execute("SET LOCAL search_path=public,pg_catalog")
    conn.execute("SET LOCAL statement_timeout='180s'")
    conn.execute("SET LOCAL lock_timeout='10s'")


def verify_target(conn) -> dict:
    identity = conn.execute(
        "SELECT id::text,schema_version FROM catalog_instance"
    ).fetchone()
    revisions = tuple(row["version"] for row in conn.execute(
        "SELECT version FROM catalog_schema_migrations ORDER BY version"
    ))
    if not identity or identity["schema_version"] != "catalog-v2" or revisions != EXPECTED_REVISIONS:
        raise RuntimeMigrationError("Target identity or revision mismatch")
    return {"catalog_instance_id": identity["id"], "schema_version": identity["schema_version"]}


def selected_maps(mapping: dict) -> tuple[dict[int, int], dict[int, int]]:
    sources, monitors = {}, {}
    for row in mapping["mappings"]:
        if row["status"] != "matched" or row.get("activation_conflict"):
            continue
        account_id = row["account"]["account_id"]
        if row["kind"] == "x_source":
            sources[row["legacy_source_id"]] = account_id
        elif row["kind"] == "youtube_monitor":
            monitors[row["legacy_monitor_id"]] = account_id
    return sources, monitors


def choose_cursor(rows: list[dict], account_id: int) -> tuple[str | None, int]:
    populated = [row for row in rows if row["last_seen_external_id"]]
    values = {str(row["last_seen_external_id"]) for row in populated}
    if not populated:
        return None, min(row["id"] for row in rows)
    if len(values) == 1:
        chosen = max(populated, key=lambda row: (row["updated_at"] or datetime.min.replace(tzinfo=timezone.utc), -row["id"]))
        return str(chosen["last_seen_external_id"]), chosen["id"]
    resolved = audit.RESOLVED_CURSOR_SOURCE_BY_ACCOUNT.get(account_id)
    chosen = next((row for row in populated if row["id"] == resolved), None)
    if not chosen:
        raise RuntimeMigrationError(f"Unresolved cursor conflict for account {account_id}")
    return str(chosen["last_seen_external_id"]), chosen["id"]


def build_plan(old_conn, new_conn) -> dict:
    target = verify_target(new_conn)
    legacy = audit.load_legacy(old_conn)
    catalog = audit.load_catalog(new_conn)
    mapping, conflicts = audit.build_mapping(legacy, catalog)
    if conflicts:
        raise RuntimeMigrationError(f"Selection has {len(conflicts)} unresolved conflicts")
    source_account, monitor_account = selected_maps(mapping)
    if not source_account or not monitor_account:
        raise RuntimeMigrationError("Reviewed source or monitor selection is empty")

    account_enabled = {
        row["account"]["account_id"]: row["account"]["collection_enabled"]
        for row in mapping["mappings"]
        if row.get("account") and row["status"] == "matched"
    }
    source_rows = [row for row in legacy["sources"] if row["id"] in source_account]
    grouped_sources = defaultdict(list)
    for row in source_rows:
        grouped_sources[source_account[row["id"]]].append(row)
    collection_states = []
    for account_id, rows in sorted(grouped_sources.items()):
        cursor, selected_source = choose_cursor(rows, account_id)
        collection_states.append({
            "external_account_id": account_id,
            "cursor_value": cursor,
            "last_seen_external_id": cursor,
            "status": "idle" if account_enabled[account_id] else "disabled",
            "next_poll_at": None,
            "last_polled_at": max((row["updated_at"] for row in rows if row["updated_at"]), default=None),
            "provider_state": {"legacy_source_ids": sorted(row["id"] for row in rows),
                               "selected_cursor_source_id": selected_source},
        })

    monitor_rows = [row for row in legacy["monitors"] if row["id"] in monitor_account]
    for row in monitor_rows:
        collection_states.append({
            "external_account_id": monitor_account[row["id"]],
            "cursor_value": None,
            "last_seen_external_id": None,
            "status": "idle" if account_enabled[monitor_account[row["id"]]] else "disabled",
            "next_poll_at": row["next_check_at"],
            "last_polled_at": row["last_checked_at"],
            "provider_state": {"legacy_monitor_id": row["id"],
                               "uploads_playlist_id": row["uploads_playlist_id"]},
        })

    selected_routes = [row for row in legacy["routes"] if row["source_id"] in source_account]
    route_groups = defaultdict(list)
    for row in selected_routes:
        key = (source_account[row["source_id"]], row["guild_id"], row["discord_channel_id"])
        route_groups[key].append(row)
    routes = []
    route_key_by_legacy = {}
    for key, rows in sorted(route_groups.items(), key=lambda item: tuple(map(str, item[0]))):
        owners = {row["discord_user_id"] for row in rows if row["discord_user_id"]}
        states = {row["is_active"] for row in rows}
        if len(owners) > 1 or len(states) > 1:
            raise RuntimeMigrationError(f"Route ownership/state conflict: {[row['id'] for row in rows]}")
        identifiers = [key[1], key[2], *owners]
        if any(not value.isdigit() for value in identifiers):
            raise RuntimeMigrationError(f"Invalid Discord identifier in routes {[row['id'] for row in rows]}")
        route = {"external_account_id": key[0], "guild_id": key[1], "channel_id": key[2],
                 "owner_discord_user_id": next(iter(owners), None),
                 "is_active": next(iter(states)),
                 "legacy_route_ids": sorted(row["id"] for row in rows)}
        routes.append(route)
        for row in rows:
            route_key_by_legacy[row["id"]] = key

    route_ids = sorted(route_key_by_legacy)
    item_rows = [dict(row) for row in old_conn.execute(
        """SELECT DISTINCT i.id,i.source_id,i.external_id,i.url,i.published_at,
                          i.raw_text,i.created_at
           FROM source_items i
           WHERE i.source_id=ANY(%s)
             AND (i.source_id=ANY(%s) OR EXISTS (
               SELECT 1 FROM notification_deliveries d
               WHERE d.source_item_id=i.id AND d.notification_route_id=ANY(%s)))
           ORDER BY i.id""",
        (list(source_account), audit.HAO_SOURCE_IDS, route_ids or [-1]),
    )]
    items_by_key, item_key_by_legacy = {}, {}
    for row in item_rows:
        if row["source_id"] not in source_account:
            raise RuntimeMigrationError(f"Selected item {row['id']} has no account mapping")
        if not row["url"] or not row["published_at"]:
            raise RuntimeMigrationError(f"Selected item {row['id']} lacks URL or published_at")
        key = (source_account[row["source_id"]], str(row["external_id"]))
        payload = {"external_account_id": key[0], "external_id": key[1],
                   "source_url": row["url"], "raw_text": row["raw_text"],
                   "published_at": row["published_at"], "collected_at": row["created_at"]}
        previous = items_by_key.get(key)
        comparable = lambda value: {name: value[name] for name in
                                    ("external_account_id", "external_id", "source_url", "raw_text", "published_at")}
        if previous and canonical(comparable(previous)) != canonical(comparable(payload)):
            raise RuntimeMigrationError(f"Conflicting item payload for {key}")
        if not previous or payload["collected_at"] < previous["collected_at"]:
            items_by_key[key] = payload
        item_key_by_legacy[row["id"]] = key

    delivery_rows = [dict(row) for row in old_conn.execute(
        """SELECT id,notification_route_id,source_item_id,discord_message_id,delivered_at
           FROM notification_deliveries
           WHERE notification_route_id=ANY(%s) ORDER BY id""", (route_ids or [-1],)
    )]
    deliveries = []
    for row in delivery_rows:
        if not row["discord_message_id"]:
            raise RuntimeMigrationError(f"Legacy delivery {row['id']} is not a confirmed success")
        if row["source_item_id"] not in item_key_by_legacy:
            raise RuntimeMigrationError(f"Delivery {row['id']} item is outside dependency closure")
        deliveries.append({"legacy_delivery_id": row["id"],
                           "legacy_route_id": row["notification_route_id"],
                           "item_key": item_key_by_legacy[row["source_item_id"]],
                           "discord_message_id": row["discord_message_id"],
                           "delivered_at": row["delivered_at"]})

    unfinished = [dict(row) for row in old_conn.execute(
        """SELECT id,monitor_id,youtube_video_id,video_title,actual_end_at,collect_after,
                  status,last_error,updated_at
           FROM youtube_channel_videos
           WHERE monitor_id=ANY(%s) AND status<>'processed' ORDER BY id""",
        (list(monitor_account),),
    )]
    video_ids = [row["youtube_video_id"] for row in unfinished]
    catalog_videos = {}
    if video_ids:
        catalog_videos = {row["platform_video_id"]: row["id"] for row in new_conn.execute(
            "SELECT platform_video_id,id FROM videos WHERE platform='youtube' AND platform_video_id=ANY(%s)",
            (video_ids,),
        )}
    jobs = [{
        "legacy_job_id": row["id"], "job_type": "youtube_collect",
        "idempotency_key": f"legacy:youtube_channel_videos:{row['id']}",
        "external_account_id": monitor_account[row["monitor_id"]],
        "video_id": catalog_videos.get(row["youtube_video_id"]),
        "payload": {"youtube_video_id": row["youtube_video_id"], "video_title": row["video_title"],
                    "actual_end_at": row["actual_end_at"], "legacy_status": row["status"]},
        "status": "retry" if row["last_error"] else "pending",
        "next_attempt_at": row["collect_after"], "last_error": row["last_error"],
    } for row in unfinished]

    plan = {
        "contract": "runtime-subset-v1", "target": target,
        "account_versions": {str(row["account"]["account_id"]): row["account"]["version"]
                             for row in mapping["mappings"] if row.get("account") and row["status"] == "matched"},
        "collection_states": collection_states,
        "routes": routes,
        "source_items": list(items_by_key.values()),
        "deliveries": deliveries,
        "worker_jobs": jobs,
        "legacy_item_keys": {str(k): list(v) for k, v in item_key_by_legacy.items()},
        "route_keys": {str(k): list(v) for k, v in route_key_by_legacy.items()},
    }
    plan["source_snapshot_hash"] = digest(plan)
    return plan


def public_manifest(plan: dict) -> dict:
    counts = {name: len(plan[name]) for name in
              ("collection_states", "routes", "source_items", "deliveries", "worker_jobs")}
    manifest = {"contract": plan["contract"], "target": plan["target"],
                "source_snapshot_hash": plan["source_snapshot_hash"], "counts": counts,
                "excluded": ["google", "x_classification", "x_youtube_autoregistration",
                             "legacy_music_catalog", "processed_youtube_jobs"],
                "approved_for_apply": False}
    manifest["manifest_hash"] = digest(manifest)
    return manifest


def assert_target_preconditions(conn, plan: dict) -> None:
    target = verify_target(conn)
    if target != plan["target"]:
        raise RuntimeMigrationError("Target database changed after dry-run")
    versions = {str(row["id"]): row["version"] for row in conn.execute(
        "SELECT id,version FROM external_accounts WHERE id=ANY(%s)",
        ([int(key) for key in plan["account_versions"]],),
    )}
    if versions != plan["account_versions"]:
        raise RuntimeMigrationError("External account versions changed after dry-run")


def apply_plan(conn, plan: dict, manifest: dict) -> dict:
    expected = public_manifest(plan)
    supplied = dict(manifest)
    approved = supplied.pop("approved_for_apply", False)
    supplied["approved_for_apply"] = False
    if not approved or supplied != expected:
        raise RuntimeMigrationError("Exact dry-run manifest with approved_for_apply=true is required")
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    assert_target_preconditions(conn, plan)
    operation_id = uuid.uuid5(NAMESPACE, expected["manifest_hash"])
    existing = conn.execute(
        "SELECT id,manifest_hash FROM runtime_migration_receipts WHERE operation_id=%s",
        (operation_id,),
    ).fetchone()
    if existing:
        if existing["manifest_hash"] != expected["manifest_hash"]:
            raise RuntimeMigrationError("Existing operation receipt hash mismatch")
        return {"applied": False, "operation_id": str(operation_id), "counts": expected["counts"]}
    occupied = conn.execute("""SELECT
      (SELECT count(*) FROM collection_states) +
      (SELECT count(*) FROM source_items) +
      (SELECT count(*) FROM notification_routes) +
      (SELECT count(*) FROM notification_deliveries) +
      (SELECT count(*) FROM worker_jobs) AS total""").fetchone()["total"]
    if occupied:
        raise RuntimeMigrationError("Runtime tables are not empty and no matching receipt exists")

    users = sorted({route["owner_discord_user_id"] for route in plan["routes"]
                    if route["owner_discord_user_id"]})
    for user_id in users:
        conn.execute("INSERT INTO discord_users(discord_user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    guilds = {}
    for route in plan["routes"]:
        guilds.setdefault(route["guild_id"], route["owner_discord_user_id"])
    for guild_id, owner in guilds.items():
        conn.execute("""INSERT INTO discord_guilds(guild_id,owner_discord_user_id)
                        VALUES (%s,%s) ON CONFLICT DO NOTHING""", (guild_id, owner))
    for route in plan["routes"]:
        conn.execute("""INSERT INTO discord_channels(channel_id,guild_id)
                        VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                     (route["channel_id"], route["guild_id"]))

    for state in plan["collection_states"]:
        conn.execute("""INSERT INTO collection_states
          (external_account_id,cursor_value,last_seen_external_id,status,next_poll_at,
           last_polled_at,provider_state) VALUES (%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (external_account_id) DO NOTHING""",
          (state["external_account_id"], state["cursor_value"], state["last_seen_external_id"],
           state["status"], state["next_poll_at"], state["last_polled_at"], Jsonb(json_ready(state["provider_state"]))))

    item_ids = {}
    for item in plan["source_items"]:
        row = conn.execute("""INSERT INTO source_items
          (external_account_id,external_id,source_url,raw_text,published_at,collected_at)
          VALUES (%s,%s,%s,%s,%s,%s)
          ON CONFLICT (external_account_id,external_id) DO UPDATE SET external_id=EXCLUDED.external_id
          RETURNING id""", tuple(item.values())).fetchone()
        item_ids[(item["external_account_id"], item["external_id"])] = row["id"]

    route_ids = {}
    for route in plan["routes"]:
        row = conn.execute("""INSERT INTO notification_routes
          (external_account_id,guild_id,channel_id,owner_discord_user_id,is_active)
          VALUES (%s,%s,%s,%s,%s)
          ON CONFLICT (external_account_id,channel_id) DO UPDATE SET channel_id=EXCLUDED.channel_id
          RETURNING id""", (route["external_account_id"], route["guild_id"], route["channel_id"],
                             route["owner_discord_user_id"], route["is_active"])).fetchone()
        route_ids[(route["external_account_id"], route["guild_id"], route["channel_id"])] = row["id"]

    for delivery in plan["deliveries"]:
        route_key = tuple(plan["route_keys"][str(delivery["legacy_route_id"])])
        conn.execute("""INSERT INTO notification_deliveries
          (route_id,source_item_id,status,attempt_count,discord_message_id,delivered_at)
          VALUES (%s,%s,'sent',1,%s,%s) ON CONFLICT (route_id,source_item_id) DO NOTHING""",
          (route_ids[route_key], item_ids[tuple(delivery["item_key"])],
           delivery["discord_message_id"], delivery["delivered_at"]))

    job_ids = {}
    for job in plan["worker_jobs"]:
        row = conn.execute("""INSERT INTO worker_jobs
          (job_type,idempotency_key,external_account_id,video_id,payload,status,next_attempt_at,last_error)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (job_type,idempotency_key) DO UPDATE SET idempotency_key=EXCLUDED.idempotency_key
          RETURNING id""", (job["job_type"], job["idempotency_key"], job["external_account_id"],
                             job["video_id"], Jsonb(json_ready(job["payload"])), job["status"],
                             job["next_attempt_at"], job["last_error"])).fetchone()
        job_ids[job["legacy_job_id"]] = row["id"]

    receipt_id = conn.execute("""INSERT INTO runtime_migration_receipts
      (operation_id,catalog_instance_id,source_fingerprint,manifest_hash,summary)
      VALUES (%s,%s,%s,%s,%s) RETURNING id""",
      (operation_id, plan["target"]["catalog_instance_id"], plan["source_snapshot_hash"],
       expected["manifest_hash"], Jsonb(expected["counts"]))).fetchone()["id"]

    def legacy_map(source_table, legacy_id, target_table, target_id, reason):
        conn.execute("""INSERT INTO runtime_legacy_id_map
          (receipt_id,source_table,legacy_id,target_table,target_id,selection_reason)
          VALUES (%s,%s,%s,%s,%s,%s)""",
          (receipt_id, source_table, str(legacy_id), target_table, str(target_id), reason))

    for state in plan["collection_states"]:
        provider = state["provider_state"]
        if "legacy_source_ids" in provider:
            for source in provider["legacy_source_ids"]:
                legacy_map("artist_sources", source, "collection_states",
                           state["external_account_id"], "reviewed account mapping")
        else:
            legacy_map("youtube_channel_monitors", provider["legacy_monitor_id"],
                       "collection_states", state["external_account_id"],
                       "reviewed account mapping")
    for legacy_id, key in plan["legacy_item_keys"].items():
        legacy_map("source_items", legacy_id, "source_items", item_ids[tuple(key)], "delivery closure or reviewed cursor boundary")
    for legacy_id, key in plan["route_keys"].items():
        legacy_map("notification_routes", legacy_id, "notification_routes", route_ids[tuple(key)], "reviewed account route")
    for delivery in plan["deliveries"]:
        route_key = tuple(plan["route_keys"][str(delivery["legacy_route_id"])])
        target_id = conn.execute("SELECT id FROM notification_deliveries WHERE route_id=%s AND source_item_id=%s",
                                 (route_ids[route_key], item_ids[tuple(delivery["item_key"])] )).fetchone()["id"]
        legacy_map("notification_deliveries", delivery["legacy_delivery_id"], "notification_deliveries", target_id, "confirmed sent delivery")
    for legacy_id, target_id in job_ids.items():
        legacy_map("youtube_channel_videos", legacy_id, "worker_jobs", target_id, "unfinished independent YouTube work")
    return {"applied": True, "operation_id": str(operation_id), "counts": expected["counts"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    legacy_url = configured_url("DATABASE_URL", ".env")
    new_url = configured_url("NEW_DATABASE_URL", ".env.catalog")
    if legacy_url == new_url:
        raise RuntimeMigrationError("Legacy and target URLs are identical")
    with psycopg.connect(legacy_url, connect_timeout=20, row_factory=dict_row) as old_conn:
        with psycopg.connect(new_url, connect_timeout=20, row_factory=dict_row) as new_conn:
            configure(old_conn, read_only=True)
            configure(new_conn, read_only=not args.apply)
            plan = build_plan(old_conn, new_conn)
            manifest = public_manifest(plan)
            if not args.apply:
                args.manifest.parent.mkdir(parents=True, exist_ok=True)
                args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result = {"dry_run": True, **manifest}
            else:
                supplied = json.loads(args.manifest.read_text(encoding="utf-8"))
                result = apply_plan(new_conn, plan, supplied)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
