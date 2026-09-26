"""Prepare and apply the reviewed legacy runtime subset to the unified DB.

The default is a read-only dry-run. ``--apply`` additionally requires the exact
dry-run manifest and is reserved for the phase-5 cutover.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.schemas.worker_jobs import JobRequest

try:
    from scripts import audit_single_db_readiness as audit
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    import audit_single_db_readiness as audit

DEFAULT_MANIFEST = (
    ROOT / "db-migration" / "reports" / "single-db-readiness"
    / "runtime-migration-manifest.json"
)
NAMESPACE = uuid.UUID("f5a9e298-502c-4d44-aea2-ab27d276370c")
EXPECTED_REVISIONS = {("001", "002"), ("001", "002", "003"), ("001", "002", "003", "004")}
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


def configured_url(variable: str, filename: str = ".env") -> str:
    if os.environ.get("NEW_DATABASE_URL") or dotenv_values(ROOT / ".env").get("NEW_DATABASE_URL"):
        raise RuntimeMigrationError("NEW_DATABASE_URL is retired; configure DATABASE_URL only")
    value = (os.environ.get(variable) or dotenv_values(ROOT / filename).get(variable) or "").strip()
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
    if not identity or identity["schema_version"] != "catalog-v2" or revisions not in EXPECTED_REVISIONS:
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


def build_plan(old_conn, new_conn, *, baseline_at: datetime | None = None) -> dict:
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

    baseline_at = baseline_at or datetime.now(timezone.utc)
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
                               "uploads_playlist_id": row["uploads_playlist_id"],
                               "youtube_baseline_at": baseline_at.isoformat()},
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
    pending_archives = [dict(row) for row in old_conn.execute(
        """SELECT a.id,a.youtube_video_id,a.attempts,a.last_checked_at,a.next_check_at,
                  a.updated_at,a.status,v.id AS channel_video_id,v.monitor_id,
                  v.status AS channel_status,v.last_error
           FROM youtube_live_archives a
           LEFT JOIN youtube_channel_videos v ON v.youtube_video_id=a.youtube_video_id
             AND v.monitor_id=ANY(%s)
           WHERE a.status='pending' ORDER BY a.id,v.id""",
        (list(monitor_account),),
    )]
    archive_by_video = defaultdict(list)
    excluded_archives = []
    for archive in pending_archives:
        if archive["channel_video_id"] is None:
            excluded_archives.append({"legacy_archive_id": archive["id"],
                                      "external_video_id": archive["youtube_video_id"],
                                      "reason": "no_approved_youtube_monitor; X_auto_registration_not_migrated"})
            continue
        if archive["attempts"] >= 168:
            excluded_archives.append({"legacy_archive_id": archive["id"],
                                      "external_video_id": archive["youtube_video_id"],
                                      "reason": "legacy_wait_limit_exhausted"})
            continue
        archive_by_video[archive["youtube_video_id"]].append(archive)
    if any(len({monitor_account[a["monitor_id"]] for a in rows}) > 1
           for rows in archive_by_video.values()):
        raise RuntimeMigrationError("Pending archive maps to multiple approved accounts")
    video_ids = list({row["youtube_video_id"] for row in unfinished} | set(archive_by_video))
    catalog_videos = {}
    if video_ids:
        catalog_videos = {row["platform_video_id"]: row for row in new_conn.execute(
            """SELECT v.platform_video_id,v.id,v.source_account_id,v.archived_at,
                      l.setlist_state AS archive_state,
                      EXISTS (SELECT 1 FROM performances p WHERE p.archive_id=l.id
                              AND p.archived_at IS NULL) AS has_performances,
                      EXISTS (SELECT 1 FROM covers c WHERE c.video_id=v.id) AS has_cover
               FROM videos v LEFT JOIN live_archives l ON l.video_id=v.id AND l.archived_at IS NULL
               WHERE v.platform='youtube' AND v.platform_video_id=ANY(%s)""",
            (video_ids,),
        )}
    channel_ids = {row["id"]: row["youtube_channel_id"] for row in monitor_rows}
    jobs = []
    excluded_work = []
    states_by_account = {s["external_account_id"]: s for s in collection_states}
    work = {}
    for row in unfinished:
        key = row["youtube_video_id"]
        account_id = monitor_account[row["monitor_id"]]
        if key in work and work[key][0] != account_id:
            raise RuntimeMigrationError("Unfinished video maps to multiple approved accounts")
        work.setdefault(key, (account_id, row))
    for external_id, archives in archive_by_video.items():
        archive = archives[0]
        account_id = monitor_account[archive["monitor_id"]]
        if external_id in work and work[external_id][0] != account_id:
            raise RuntimeMigrationError("Archive and channel work account mismatch")
        work.setdefault(external_id, (account_id, None))
    for external_id, (account_id, channel_row) in sorted(work.items()):
        existing_video = catalog_videos.get(external_id)
        if existing_video and (existing_video["archived_at"] is not None or
                               existing_video["source_account_id"] not in (None, account_id)):
            raise RuntimeMigrationError("Existing catalog video ownership or archived-state conflict")
        archives = archive_by_video.get(external_id, [])
        if channel_row and not archives and channel_row["collect_after"] is None and channel_row["actual_end_at"] is None:
            states_by_account[account_id]["provider_state"].setdefault("youtube_pending_video_ids", []).append(external_id)
            excluded_work.append({"external_video_id": external_id,
                                  "reason": "awaiting_video_end_in_poll_state",
                                  "account_id": account_id,
                                  "catalog_video_id": existing_video["id"] if existing_video else None,
                                  "legacy_channel_video_id": channel_row["id"],
                                  "legacy_archive_ids": []})
            continue
        skip_reason = None
        if existing_video:
            if existing_video.get("has_performances"):
                skip_reason = "catalog_archive_already_has_performances"
            elif existing_video.get("archive_state") == "complete":
                skip_reason = "catalog_archive_marked_complete"
            elif existing_video.get("has_cover"):
                skip_reason = "catalog_video_is_cover"
        if skip_reason:
            excluded_work.append({"external_video_id": external_id, "reason": skip_reason,
                                  "account_id": account_id,
                                  "catalog_video_id": existing_video["id"],
                                  "legacy_channel_video_id": channel_row["id"] if channel_row else None,
                                  "legacy_archive_ids": sorted({a["id"] for a in archives})})
            continue
        # Several legacy source rows can point to the same channel video. One
        # current worker job resumes the external video; retain every old row.
        archive = max(archives, key=lambda row: (row["attempts"], row["last_checked_at"] or datetime.min.replace(tzinfo=timezone.utc))) if archives else None
        monitor_id = archive["monitor_id"] if archive else channel_row["monitor_id"]
        channel_id = channel_ids[monitor_id]
        if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", external_id):
            raise RuntimeMigrationError("Invalid approved YouTube channel or video ID")
        wait_count = int(archive["attempts"]) if archive else 0
        archive_next_check = min(a["next_check_at"] for a in archives) if archives else None
        archive_last_check = max((a["last_checked_at"] for a in archives if a["last_checked_at"]), default=None)
        payload = dict(channel_id=channel_id, youtube_video_id=external_id,
                       purpose="archive", wait_count=wait_count)
        request = JobRequest(job_type="youtube_collect", external_account_id=account_id,
                             video_id=existing_video["id"] if existing_video else None, payload=payload)
        last_error = (channel_row or {}).get("last_error")
        jobs.append({"legacy_job_id": channel_row["id"] if channel_row else None,
                     "legacy_archive_ids": sorted({a["id"] for a in archives}),
                     "legacy_archive_states": [dict(id=a["id"], attempts=a["attempts"],
                                                    last_checked_at=a["last_checked_at"],
                                                    next_check_at=a["next_check_at"]) for a in archives],
                     "job_type": "youtube_collect", "idempotency_key": request.key(),
                     "external_account_id": account_id, "video_id": request.video_id,
                     "external_video_id": external_id,
                     "payload": request.parsed_payload().model_dump(),
                     "status": "retry" if last_error else "pending",
                     "next_attempt_at": archive_next_check if archive else (
                         channel_row["collect_after"] or (channel_row["actual_end_at"] + timedelta(hours=24)
                             if channel_row["actual_end_at"] else None)),
                     "last_checked_at": archive_last_check,
                     "attempt_count": 0,
                     "legacy_wait_count": wait_count,
                     "last_error": last_error})

    for job in jobs:
        state = states_by_account[job["external_account_id"]]
        if job["legacy_job_id"] is not None and job["next_attempt_at"] is None:
            state["provider_state"].setdefault("youtube_pending_video_ids", []).append(job["external_video_id"])
        if job["legacy_archive_ids"]:
            state["provider_state"].setdefault("youtube_legacy_pending_checks", {})[job["external_video_id"]] = {
                "archive_ids": job["legacy_archive_ids"],
                "wait_count": job["legacy_wait_count"],
                "last_checked_at": job["last_checked_at"].isoformat() if job["last_checked_at"] else None,
            }

    plan = {
        "contract": "runtime-subset-v3", "target": target,
        "baseline_at": baseline_at,
        "account_versions": {str(row["account"]["account_id"]): row["account"]["version"]
                             for row in mapping["mappings"] if row.get("account") and row["status"] == "matched"},
        "collection_states": collection_states,
        "routes": routes,
        "source_items": list(items_by_key.values()),
        "deliveries": deliveries,
        "worker_jobs": jobs,
        "excluded_archives": excluded_archives,
        "excluded_work": excluded_work,
        "legacy_item_keys": {str(k): list(v) for k, v in item_key_by_legacy.items()},
        "route_keys": {str(k): list(v) for k, v in route_key_by_legacy.items()},
    }
    plan["source_snapshot_hash"] = digest(plan)
    return plan


def public_manifest(plan: dict) -> dict:
    counts = {name: len(plan[name]) for name in
              ("collection_states", "routes", "source_items", "deliveries", "worker_jobs")}
    manifest = {"contract": plan["contract"], "target": plan["target"],
                "merge_policy": "preserve-existing-runtime-v1",
                "baseline_at": (plan["baseline_at"].isoformat() if isinstance(plan.get("baseline_at"), datetime)
                                else plan.get("baseline_at")),
                "source_snapshot_hash": plan["source_snapshot_hash"], "counts": counts,
                "selected_accounts": plan["account_versions"],
                "x_cursors": [{"account_id": s["external_account_id"],
                                "legacy_source_ids": s["provider_state"]["legacy_source_ids"],
                                "last_seen_external_id": s["last_seen_external_id"]}
                               for s in plan["collection_states"] if "legacy_source_ids" in s["provider_state"]],
                "route_owners": [{"account_id": r["external_account_id"],
                                  "legacy_route_ids": r["legacy_route_ids"],
                                  "guild_id": r["guild_id"], "channel_id": r["channel_id"],
                                  "owner_discord_user_id": r["owner_discord_user_id"]}
                                 for r in plan["routes"]],
                "sent_delivery_ids": [d["legacy_delivery_id"] for d in plan["deliveries"]],
                "source_item_mapping": [{"legacy_item_id": int(legacy_id),
                                         "account_id": key[0], "external_id": key[1]}
                                        for legacy_id, key in sorted(plan["legacy_item_keys"].items(),
                                                                     key=lambda pair: int(pair[0]))],
                "youtube_work": [{"external_video_id": j["external_video_id"],
                                  "account_id": j["external_account_id"],
                                  "legacy_channel_video_id": j["legacy_job_id"],
                                  "legacy_archive_ids": j["legacy_archive_ids"],
                                  "legacy_archive_states": j.get("legacy_archive_states", []),
                                  "catalog_video_id": j["video_id"],
                                  "wait_count": j["legacy_wait_count"],
                                  "last_checked_at": j["last_checked_at"],
                                  "next_attempt_at": j["next_attempt_at"],
                                  "status": j["status"], "last_error_present": bool(j["last_error"])}
                                 for j in plan["worker_jobs"]],
                "excluded_archives": plan.get("excluded_archives", []),
                "excluded_work": plan.get("excluded_work", []),
                "excluded": {"google": "legacy_data_preserved", "x_classification": "feature_removed",
                             "x_youtube_autoregistration": "feature_removed",
                             "legacy_music_catalog": "outside_selected_runtime_subset",
                             "processed_youtube_jobs": "historical_completed_work"},
                "approved_for_apply": False}
    manifest = json_ready(manifest)
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


def lock_target_for_merge(conn) -> None:
    # A live collector does not participate in the advisory lock. Serialize its
    # DB writes while verifying and importing the selected legacy subset.
    conn.execute("""LOCK TABLE external_accounts, collection_states, source_items,
        discord_users, discord_guilds, discord_channels, notification_routes,
        notification_deliveries, worker_jobs IN SHARE ROW EXCLUSIVE MODE""")


def merge_cursor(old: str | None, current: str | None) -> str | None:
    if not old:
        return current
    if not current:
        return old
    if old == current:
        return current
    if old.isdigit() and current.isdigit():
        return str(max(int(old), int(current)))
    raise RuntimeMigrationError("Existing and legacy X cursors cannot be ordered")


def merge_provider_state(current: dict, legacy: dict) -> dict:
    merged = dict(current)
    for key, value in legacy.items():
        if key == "youtube_pending_video_ids":
            merged[key] = list(dict.fromkeys([*merged.get(key, []), *value]))
        elif key == "youtube_legacy_pending_checks":
            for video_id, details in value.items():
                if video_id in merged.get(key, {}) and merged[key][video_id] != details:
                    raise RuntimeMigrationError("Existing YouTube pending check conflicts with legacy")
            merged[key] = {**merged.get(key, {}), **value}
        elif key == "youtube_baseline_at":
            merged.setdefault(key, value)
        elif key in merged and merged[key] != value:
            raise RuntimeMigrationError(f"Existing provider state conflicts on {key}")
        else:
            merged[key] = value
    return merged


def validate_existing_runtime(conn, plan: dict) -> dict:
    account_ids = [state["external_account_id"] for state in plan["collection_states"]]
    states = {row["external_account_id"]: row for row in conn.execute(
        """SELECT external_account_id,cursor_value,last_seen_external_id,status,
                  lease_expires_at,provider_state FROM collection_states
           WHERE external_account_id=ANY(%s)""", (account_ids,))}
    for state in plan["collection_states"]:
        current = states.get(state["external_account_id"])
        if not current:
            continue
        if "legacy_source_ids" in state["provider_state"]:
            merge_cursor(state["cursor_value"], current["cursor_value"])
            merge_cursor(state["last_seen_external_id"], current["last_seen_external_id"])
        elif current["status"] == "polling" and current["lease_expires_at"]:
            raise RuntimeMigrationError("Active YouTube poll must finish before runtime merge")
        merge_provider_state(current["provider_state"], state["provider_state"])

    existing_items = {(row["external_account_id"], row["external_id"]): row for row in conn.execute(
        """SELECT external_account_id,external_id,source_url,raw_text,published_at
           FROM source_items WHERE external_account_id=ANY(%s)""", (account_ids,))}
    body_differences = 0
    for item in plan["source_items"]:
        current = existing_items.get((item["external_account_id"], item["external_id"]))
        if not current:
            continue
        if current["source_url"] != item["source_url"] or current["published_at"] != item["published_at"]:
            raise RuntimeMigrationError("Existing source item URL or publication time conflicts with legacy")
        body_differences += current["raw_text"] != item["raw_text"]

    route_keys = {(r["external_account_id"], r["channel_id"]): r for r in plan["routes"]}
    for route in conn.execute("""SELECT external_account_id,guild_id,channel_id,
                               owner_discord_user_id,is_active FROM notification_routes"""):
        planned = route_keys.get((route["external_account_id"], route["channel_id"]))
        if planned and any(route[field] != planned[field] for field in
                           ("guild_id", "owner_discord_user_id", "is_active")):
            raise RuntimeMigrationError("Existing notification route conflicts with legacy")
    if conn.execute("SELECT 1 FROM notification_deliveries LIMIT 1").fetchone():
        raise RuntimeMigrationError("Existing deliveries need a separate conflict review")
    job_keys = {(j["job_type"], j["idempotency_key"]) for j in plan["worker_jobs"]}
    for job in conn.execute("SELECT job_type,idempotency_key FROM worker_jobs"):
        if (job["job_type"], job["idempotency_key"]) in job_keys:
            raise RuntimeMigrationError("Existing worker job conflicts with legacy")
    return {"existing_states": len(states), "existing_item_body_differences": body_differences}


def completed_receipt(conn, manifest: dict) -> dict | None:
    if not manifest.get("approved_for_apply"):
        return None
    body = dict(manifest)
    manifest_hash = body.pop("manifest_hash", None)
    body["approved_for_apply"] = False
    if not manifest_hash or digest(body) != manifest_hash:
        raise RuntimeMigrationError("Approved manifest hash is invalid")
    if verify_target(conn) != manifest["target"]:
        raise RuntimeMigrationError("Target database changed after dry-run")
    operation_id = uuid.uuid5(NAMESPACE, manifest_hash)
    existing = conn.execute("""SELECT manifest_hash FROM runtime_migration_receipts
                               WHERE operation_id=%s""", (operation_id,)).fetchone()
    if not existing:
        return None
    if existing["manifest_hash"] != manifest_hash:
        raise RuntimeMigrationError("Existing operation receipt hash mismatch")
    return {"applied": False, "operation_id": str(operation_id), "counts": manifest["counts"]}


def apply_plan(conn, plan: dict, manifest: dict) -> dict:
    expected = public_manifest(plan)
    supplied = dict(manifest)
    approved = supplied.pop("approved_for_apply", False)
    supplied["approved_for_apply"] = False
    if not approved or supplied != expected:
        raise RuntimeMigrationError("Exact dry-run manifest with approved_for_apply=true is required")
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    lock_target_for_merge(conn)
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
    merge_audit = validate_existing_runtime(conn, plan)

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
        current = conn.execute("""SELECT cursor_value,last_seen_external_id,status,
                               next_poll_at,provider_state FROM collection_states
                               WHERE external_account_id=%s""",
                               (state["external_account_id"],)).fetchone()
        if current:
            provider_state = merge_provider_state(current["provider_state"], state["provider_state"])
            is_x = "legacy_source_ids" in state["provider_state"]
            cursor = merge_cursor(state["cursor_value"], current["cursor_value"]) if is_x else current["cursor_value"]
            last_seen = merge_cursor(state["last_seen_external_id"], current["last_seen_external_id"]) if is_x else current["last_seen_external_id"]
            if is_x and cursor:
                provider_state["x_baseline_initialized"] = True
            was_polling = is_x and current["status"] == "polling"
            # A collector holding an old in-memory baseline must fail its lease
            # check. Delay a fresh claim beyond that lease's lifetime.
            conn.execute("""UPDATE collection_states SET cursor_value=%s,
              last_seen_external_id=%s,provider_state=%s,
              status=CASE WHEN %s THEN 'idle' ELSE status END,
              lease_owner=CASE WHEN %s THEN NULL ELSE lease_owner END,
              lease_expires_at=CASE WHEN %s THEN NULL ELSE lease_expires_at END,
              next_poll_at=CASE WHEN %s THEN clock_timestamp()+interval '10 minutes'
                                ELSE next_poll_at END
              WHERE external_account_id=%s""",
              (cursor,last_seen,Jsonb(json_ready(provider_state)),was_polling,was_polling,
               was_polling,was_polling,state["external_account_id"]))
            continue
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
        if job["legacy_job_id"] is not None:
            job_ids[job["legacy_job_id"]] = row["id"]
        for archive_id in job["legacy_archive_ids"]:
            job_ids[("youtube_live_archives", archive_id)] = row["id"]

    receipt_id = conn.execute("""INSERT INTO runtime_migration_receipts
      (operation_id,catalog_instance_id,source_fingerprint,manifest_hash,summary)
      VALUES (%s,%s,%s,%s,%s) RETURNING id""",
      (operation_id, plan["target"]["catalog_instance_id"], plan["source_snapshot_hash"],
       expected["manifest_hash"], Jsonb({**expected["counts"], **merge_audit}))).fetchone()["id"]

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
        table, value = legacy_id if isinstance(legacy_id, tuple) else ("youtube_channel_videos", legacy_id)
        legacy_map(table, value, "worker_jobs", target_id, "approved independent YouTube resume work")
    return {"applied": True, "operation_id": str(operation_id), "counts": expected["counts"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    legacy_url = configured_url("LEGACY_DATABASE_URL")
    new_url = configured_url("DATABASE_URL")
    if legacy_url == new_url:
        raise RuntimeMigrationError("Legacy and target URLs are identical")
    try:
        with psycopg.connect(legacy_url, connect_timeout=20, row_factory=dict_row) as old_conn:
            with psycopg.connect(new_url, connect_timeout=20, row_factory=dict_row) as new_conn:
                configure(old_conn, read_only=True)
                configure(new_conn, read_only=not args.apply)
                supplied = json.loads(args.manifest.read_text(encoding="utf-8")) if args.apply else None
                baseline = datetime.fromisoformat(supplied["baseline_at"]) if supplied else None
                if args.apply:
                    completed = completed_receipt(new_conn, supplied)
                    if completed:
                        print(json.dumps(completed, ensure_ascii=False))
                        return 0
                    new_conn.rollback()
                    configure(new_conn, read_only=False)
                    lock_target_for_merge(new_conn)
                plan = build_plan(old_conn, new_conn, baseline_at=baseline)
                if args.apply:
                    # The source snapshot is fully materialized in plan. Do not
                    # keep an idle legacy read transaction open for the long
                    # target write/receipt phase.
                    old_conn.rollback()
                manifest = public_manifest(plan)
                if not args.apply:
                    args.manifest.parent.mkdir(parents=True, exist_ok=True)
                    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    result = {"dry_run": True, "manifest": str(args.manifest),
                              "manifest_hash": manifest["manifest_hash"], "counts": manifest["counts"],
                              "excluded_archive_count": len(manifest["excluded_archives"]),
                              "excluded_work_count": len(manifest["excluded_work"])}
                else:
                    result = apply_plan(new_conn, plan, supplied)
    except psycopg.Error as error:
        state = error.sqlstate or "connection"
        raise RuntimeMigrationError(
            f"Database operation failed (SQLSTATE {state}); check the target receipt before retrying"
        ) from None
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
