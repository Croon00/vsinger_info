"""Read-only inventory for the legacy-to-catalog runtime consolidation.

This command never imports app.core.db and never calls application services. It
opens both PostgreSQL connections in read-only transactions and writes only
sanitized JSON reports under the git-ignored db-migration/reports directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "db-migration" / "reports" / "single-db-readiness"
WRITER_PATTERNS = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|init_db\s*\(|\.commit\s*\()",
    re.IGNORECASE,
)
LEGACY_TABLES = {
    "artists",
    "artist_sources",
    "source_items",
    "youtube_live_archives",
    "youtube_song_performances",
    "youtube_cover_videos",
    "youtube_cover_collaborators",
    "karaoke_source_matches",
    "youtube_channel_monitors",
    "youtube_channel_videos",
    "notification_routes",
    "notification_deliveries",
    "event_candidates",
    "google_oauth_tokens",
    "calendar_syncs",
    "songs",
    "song_lyrics",
}
LEGACY_X_HANDLE_ALIASES = {
    "imi_rkmusic": "imi0131",
    "honkthehorn": "honkthehorn_",
    "haru_saruhi": "harusaruhi",
}
LEGACY_X_EXCLUDED_SOURCE_IDS = {12, 72, 73}
RESOLVED_CURSOR_SOURCE_BY_ACCOUNT = {31: 14, 58: 87479}
HAO_SOURCE_IDS = [14, 79779]


def load_url(variable: str, filename: str) -> str:
    value = (os.environ.get(variable) or dotenv_values(ROOT / filename).get(variable) or "").strip()
    if not value:
        raise RuntimeError(f"{variable} is not configured in {filename}")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError(f"{variable} is not a PostgreSQL URL")
    return value


def configure_read_only(conn: psycopg.Connection) -> None:
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL search_path=public,pg_catalog")
    conn.execute("SET LOCAL statement_timeout='120s'")
    conn.execute("SET LOCAL lock_timeout='5s'")


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_value) + "\n",
        encoding="utf-8",
    )


def opaque(value: str | None) -> str | None:
    if not value:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def normalized_handle(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlsplit(candidate)
        candidate = parsed.path.strip("/").split("/")[0]
    candidate = candidate.lstrip("@").casefold()
    return candidate or None


def table_columns(conn, table: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s""",
            (table,),
        )
    }


def scalar(conn, query: str, params=()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(next(iter(row.values())))


def load_legacy(conn) -> dict:
    sources = [dict(row) for row in conn.execute(
        """SELECT s.id,s.artist_id,s.source_type,s.label,s.value,s.external_user_id,
                  s.last_seen_external_id,s.is_active,s.updated_at,
                  a.name AS artist_name,a.discord_user_id,
                  (SELECT count(*) FROM notification_routes r WHERE r.source_id=s.id) AS route_count,
                  (SELECT count(*) FROM source_items i WHERE i.source_id=s.id) AS item_count,
                  (SELECT count(*) FROM notification_deliveries d
                    JOIN notification_routes r ON r.id=d.notification_route_id
                    WHERE r.source_id=s.id) AS delivery_count
           FROM artist_sources s JOIN artists a ON a.id=s.artist_id
           ORDER BY s.id"""
    ).fetchall()]
    routes = [dict(row) for row in conn.execute(
        """SELECT r.id,r.source_id,r.item_type,r.is_active,r.updated_at,
                  r.discord_user_id,r.guild_id,r.discord_channel_id,
                  count(d.id) AS delivery_count,
                  count(d.id) FILTER (WHERE d.discord_message_id IS NOT NULL) AS sent_count
           FROM notification_routes r
           LEFT JOIN notification_deliveries d ON d.notification_route_id=r.id
           GROUP BY r.id ORDER BY r.id"""
    ).fetchall()]
    monitors = [dict(row) for row in conn.execute(
        """SELECT m.id,m.artist_name,m.youtube_channel_id,m.channel_title,m.channel_url,
                  m.uploads_playlist_id,m.is_active,m.last_checked_at,m.next_check_at,
                  m.updated_at,m.discord_user_id,
                  count(v.id) AS video_count,
                  count(v.id) FILTER (WHERE v.status <> 'processed') AS unfinished_count
           FROM youtube_channel_monitors m
           LEFT JOIN youtube_channel_videos v ON v.monitor_id=m.id
           GROUP BY m.id ORDER BY m.id"""
    ).fetchall()]
    video_status = [dict(row) for row in conn.execute(
        """SELECT m.id AS monitor_id,v.status,count(*) AS row_count,
                  count(*) FILTER (WHERE v.archive_id IS NOT NULL) AS with_archive
           FROM youtube_channel_monitors m
           JOIN youtube_channel_videos v ON v.monitor_id=m.id
           GROUP BY m.id,v.status ORDER BY m.id,v.status"""
    ).fetchall()]
    return {"sources": sources, "routes": routes, "monitors": monitors, "video_status": video_status}


def load_catalog(conn) -> dict:
    identity = dict(conn.execute(
        "SELECT id,schema_version,initial_import_id,initialized_at FROM catalog_instance"
    ).fetchone())
    revision = dict(conn.execute(
        "SELECT version,checksum,applied_at FROM catalog_schema_migrations ORDER BY version DESC LIMIT 1"
    ).fetchone())
    accounts = [dict(row) for row in conn.execute(
        """SELECT e.id,e.platform,e.platform_id,e.handle,e.url,e.collection_enabled,
                  e.archived_at,e.version,e.updated_at,
                  COALESCE(array_agg(a.name_native ORDER BY a.name_native)
                    FILTER (WHERE a.id IS NOT NULL),'{}') AS artist_names
           FROM external_accounts e
           LEFT JOIN artist_external_accounts ae ON ae.account_id=e.id
           LEFT JOIN artists a ON a.id=ae.artist_id
           GROUP BY e.id ORDER BY e.platform,e.id"""
    ).fetchall()]
    return {"identity": identity, "revision": revision, "accounts": accounts}


def account_indexes(accounts: list[dict]) -> tuple[dict, dict]:
    by_fixed: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_handle: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for account in accounts:
        if account["platform_id"]:
            by_fixed[(account["platform"], str(account["platform_id"]))].append(account)
        handles = {normalized_handle(account["handle"]), normalized_handle(account["url"])} - {None}
        for handle in handles:
            by_handle[(account["platform"], handle)].append(account)
    return by_fixed, by_handle


def public_account(account: dict) -> dict:
    return {
        "account_id": account["id"],
        "platform": account["platform"],
        "platform_id": account["platform_id"],
        "handle": account["handle"],
        "url": account["url"],
        "collection_enabled": account["collection_enabled"],
        "archived": account["archived_at"] is not None,
        "version": account["version"],
        "artist_names": account["artist_names"],
    }


def match_account(platform: str, fixed_id: str | None, handle: str | None, by_fixed, by_handle) -> dict:
    fixed = by_fixed.get((platform, str(fixed_id)), []) if fixed_id else []
    candidates = by_handle.get((platform, normalized_handle(handle)), []) if normalized_handle(handle) else []
    if len(fixed) == 1:
        account = fixed[0]
        conflicts = [row["id"] for row in candidates if row["id"] != account["id"]]
        return {"status": "conflict" if conflicts else "matched", "evidence": "platform_id",
                "account": public_account(account), "conflicting_account_ids": conflicts}
    if len(fixed) > 1:
        return {"status": "conflict", "evidence": "duplicate_platform_id",
                "candidate_account_ids": [row["id"] for row in fixed]}
    if len(candidates) == 1:
        account = candidates[0]
        return {"status": "matched", "evidence": "handle",
                "legacy_platform_id_differs": bool(
                    fixed_id and str(fixed_id) != str(account.get("platform_id") or "")
                ),
                "account": public_account(account)}
    if len(candidates) > 1:
        return {"status": "conflict", "evidence": "ambiguous_handle",
                "candidate_account_ids": [row["id"] for row in candidates]}
    return {"status": "missing_account", "evidence": "none"}


def build_mapping(legacy: dict, catalog: dict) -> tuple[dict, list[dict]]:
    by_fixed, by_handle = account_indexes(catalog["accounts"])
    mappings = []
    conflicts = []
    for source in legacy["sources"]:
        if source["id"] in LEGACY_X_EXCLUDED_SOURCE_IDS:
            match = {"status": "excluded", "evidence": "confirmed_invalid_legacy_account"}
        elif source["source_type"] != "x":
            match = {"status": "excluded", "evidence": "unsupported_source_type"}
        else:
            legacy_handle = normalized_handle(source["value"])
            mapped_handle = LEGACY_X_HANDLE_ALIASES.get(legacy_handle, source["value"])
            match = match_account("x", source["external_user_id"], mapped_handle, by_fixed, by_handle)
        item = {
            "kind": "x_source",
            "legacy_source_id": source["id"],
            "legacy_artist_id": source["artist_id"],
            "artist_name": source["artist_name"],
            "legacy_handle": source["value"],
            "matched_handle": mapped_handle,
            "legacy_platform_id": source["external_user_id"],
            "legacy_active": source["is_active"],
            "cursor_present": source["last_seen_external_id"] is not None,
            "cursor_fingerprint": opaque(source["last_seen_external_id"]),
            "owner_fingerprint": opaque(source["discord_user_id"]),
            "route_count": source["route_count"],
            "item_count": source["item_count"],
            "delivery_count": source["delivery_count"],
            **match,
        }
        account = match.get("account")
        if account:
            item["activation_conflict"] = bool(
                source["is_active"] and (not account["collection_enabled"] or account["archived"])
            )
        mappings.append(item)
        if item["status"] not in {"matched", "excluded"} or item.get("activation_conflict"):
            conflicts.append({"kind": "x_source", "legacy_id": source["id"],
                              "status": item["status"], "activation_conflict": item.get("activation_conflict", False),
                              "recommended_action": "hold_until_account_identity_and_activation_are_reviewed"})

    for monitor in legacy["monitors"]:
        match = match_account("youtube", monitor["youtube_channel_id"], monitor["channel_url"], by_fixed, by_handle)
        item = {
            "kind": "youtube_monitor",
            "legacy_monitor_id": monitor["id"],
            "artist_name": monitor["artist_name"],
            "channel_title": monitor["channel_title"],
            "legacy_platform_id": monitor["youtube_channel_id"],
            "legacy_active": monitor["is_active"],
            "last_checked_at": monitor["last_checked_at"],
            "next_check_at": monitor["next_check_at"],
            "video_count": monitor["video_count"],
            "unfinished_count": monitor["unfinished_count"],
            "owner_fingerprint": opaque(monitor["discord_user_id"]),
            **match,
        }
        account = match.get("account")
        if account:
            item["activation_conflict"] = bool(
                monitor["is_active"] and (not account["collection_enabled"] or account["archived"])
            )
        mappings.append(item)
        if item["status"] != "matched" or item.get("activation_conflict"):
            conflicts.append({"kind": "youtube_monitor", "legacy_id": monitor["id"],
                              "status": item["status"], "activation_conflict": item.get("activation_conflict", False),
                              "recommended_action": "hold_until_account_identity_and_activation_are_reviewed"})

    source_by_id = {row["id"]: row for row in legacy["sources"]}
    account_groups: dict[int, list[dict]] = defaultdict(list)
    for item in mappings:
        if item["kind"] == "x_source" and item["status"] == "matched":
            account_groups[item["account"]["account_id"]].append(item)
    for account_id, group in account_groups.items():
        cursor_groups: dict[str, list[int]] = defaultdict(list)
        for item in group:
            cursor = source_by_id[item["legacy_source_id"]]["last_seen_external_id"]
            if cursor:
                cursor_groups[str(cursor)].append(item["legacy_source_id"])
        if len(cursor_groups) <= 1:
            continue
        def cursor_key(value: str):
            return (len(value), value)
        newest = max(cursor_groups, key=cursor_key)
        newest_ids = cursor_groups[newest]
        for item in group:
            if item["legacy_source_id"] in newest_ids:
                item["cursor_order"] = "newest"
            elif item["cursor_present"]:
                item["cursor_order"] = "older"
        resolved_source_id = RESOLVED_CURSOR_SOURCE_BY_ACCOUNT.get(account_id)
        if resolved_source_id in [item["legacy_source_id"] for item in group]:
            for item in group:
                item["cursor_resolution"] = (
                    "selected" if item["legacy_source_id"] == resolved_source_id else "superseded"
                )
            continue
        conflicts.append({
            "kind": "x_cursor",
            "account_id": account_id,
            "legacy_source_ids": [item["legacy_source_id"] for item in group],
            "newest_cursor_source_ids": newest_ids,
            "status": "conflict",
            "recommended_action": "review_source_lineage_before_selecting_one_account_cursor",
        })

    summary = Counter((row["kind"], row["status"]) for row in mappings)
    return {
        "generated_at": datetime.now(timezone.utc),
        "catalog_identity": catalog["identity"],
        "catalog_revision": catalog["revision"],
        "summary": {f"{kind}:{status}": count for (kind, status), count in sorted(summary.items())},
        "mappings": mappings,
    }, conflicts


def selected_ids(mapping: dict, kind: str, key: str) -> list[int]:
    return [row[key] for row in mapping["mappings"]
            if row["kind"] == kind and row["status"] == "matched"
            and not row.get("activation_conflict")]


def build_manifest(old_conn, new_conn, mapping: dict, legacy: dict) -> dict:
    source_ids = selected_ids(mapping, "x_source", "legacy_source_id")
    monitor_ids = selected_ids(mapping, "youtube_monitor", "legacy_monitor_id")
    route_ids = [row["id"] for row in legacy["routes"] if row["source_id"] in source_ids]
    params_sources = (source_ids or [-1],)
    params_routes = (route_ids or [-1],)
    params_monitors = (monitor_ids or [-1],)
    selected_deliveries = scalar(old_conn,
        "SELECT count(*) FROM notification_deliveries WHERE notification_route_id = ANY(%s)", params_routes)
    selected_items = scalar(old_conn,
        """SELECT count(*) FROM source_items i
           WHERE i.source_id=ANY(%s)
              OR i.id IN (
                SELECT source_item_id FROM notification_deliveries
                WHERE notification_route_id=ANY(%s)
              )""", (HAO_SOURCE_IDS, route_ids or [-1]))
    successful_as_pending = scalar(old_conn,
        """SELECT count(*) FROM notification_deliveries
           WHERE notification_route_id = ANY(%s) AND discord_message_id IS NULL""", params_routes)
    unfinished_videos = scalar(old_conn,
        """SELECT count(*) FROM youtube_channel_videos
           WHERE monitor_id = ANY(%s) AND status <> 'processed'""", params_monitors)
    legacy_video_ids = [next(iter(row.values())) for row in old_conn.execute(
        """SELECT DISTINCT youtube_video_id FROM youtube_channel_videos
           WHERE monitor_id = ANY(%s) AND status='processed'""", params_monitors).fetchall()]
    existing_catalog_videos = 0
    if legacy_video_ids:
        existing_catalog_videos = scalar(new_conn,
            "SELECT count(*) FROM videos WHERE platform='youtube' AND platform_video_id = ANY(%s)",
            (legacy_video_ids,))
    selected_source_rows = scalar(old_conn, "SELECT count(*) FROM artist_sources WHERE id=ANY(%s)", params_sources)
    selected_monitor_rows = scalar(old_conn, "SELECT count(*) FROM youtube_channel_monitors WHERE id=ANY(%s)", params_monitors)
    duplicate_source_analysis = []
    grouped_sources: dict[int, list[dict]] = defaultdict(list)
    for item in mapping["mappings"]:
        if item["kind"] == "x_source" and item["status"] == "matched":
            grouped_sources[item["account"]["account_id"]].append(item)
    for account_id, group in grouped_sources.items():
        if len(group) < 2:
            continue
        ids = [item["legacy_source_id"] for item in group]
        totals = old_conn.execute(
            """WITH selected AS (
                 SELECT source_id,external_id,url,raw_text,published_at
                 FROM source_items WHERE source_id=ANY(%s)
               ), grouped AS (
                 SELECT external_id,count(DISTINCT source_id) AS source_count,
                        count(DISTINCT ROW(COALESCE(url,''),raw_text,published_at)) AS payload_count
                 FROM selected GROUP BY external_id
               )
               SELECT (SELECT count(*) FROM selected) AS total_rows,
                      count(*) AS distinct_external_ids,
                      count(*) FILTER (WHERE source_count>1) AS overlapping_external_ids,
                      count(*) FILTER (WHERE source_count>1 AND payload_count>1) AS payload_conflicts
               FROM grouped""",
            (ids,),
        ).fetchone()
        per_source = [dict(row) for row in old_conn.execute(
            """SELECT i.source_id,count(*) AS total_rows,
                      count(*) FILTER (WHERE NOT EXISTS (
                        SELECT 1 FROM source_items other
                        WHERE other.source_id=ANY(%s) AND other.source_id<>i.source_id
                          AND other.external_id=i.external_id
                      )) AS unique_to_source
               FROM source_items i WHERE i.source_id=ANY(%s)
               GROUP BY i.source_id ORDER BY i.source_id""",
            (ids, ids),
        ).fetchall()]
        duplicate_source_analysis.append({
            "account_id": account_id,
            "account_handle": group[0]["account"]["handle"],
            "legacy_source_ids": ids,
            "total_rows": totals["total_rows"],
            "distinct_external_ids": totals["distinct_external_ids"],
            "overlapping_external_ids": totals["overlapping_external_ids"],
            "overlap_payload_conflicts": totals["payload_conflicts"],
            "per_source": per_source,
        })
    return {
        "generated_at": datetime.now(timezone.utc),
        "selection_policy": "exact_platform_id_match_and_no_activation_conflict",
        "tables": {
            "artist_sources": {"rows": selected_source_rows,
                "fields": ["external_user_id", "last_seen_external_id", "is_active", "updated_at"],
                "reason": "x polling resume state"},
            "notification_routes": {"rows": len(route_ids),
                "fields": ["discord_user_id", "guild_id", "discord_channel_id", "is_active", "updated_at"],
                "reason": "account-scoped Discord destination; item_type excluded"},
            "notification_deliveries": {"rows": selected_deliveries,
                "fields": ["notification_route_id", "source_item_id", "discord_message_id", "delivered_at"],
                "reason": "successful-delivery deduplication"},
            "source_items": {"rows": selected_items,
                "fields": ["source_id", "external_id", "url", "published_at", "raw_text", "created_at"],
                "reason": "delivery dependency closure plus reviewed Hao_RKM source union; classification excluded"},
            "youtube_channel_monitors": {"rows": selected_monitor_rows,
                "fields": ["youtube_channel_id", "uploads_playlist_id", "is_active", "last_checked_at", "next_check_at", "updated_at"],
                "reason": "independent YouTube polling resume state"},
            "youtube_channel_videos_unfinished": {"rows": unfinished_videos,
                "fields": ["monitor_id", "youtube_video_id", "actual_end_at", "collect_after", "status", "last_error", "updated_at"],
                "reason": "verified unfinished/retry work only"},
        },
        "checks": {
            "selected_delivery_rows_without_message_id": successful_as_pending,
            "processed_legacy_channel_video_ids": len(legacy_video_ids),
            "processed_video_ids_already_in_catalog": existing_catalog_videos,
            "processed_video_ids_missing_from_catalog": len(legacy_video_ids) - existing_catalog_videos,
        },
        "duplicate_source_analysis": duplicate_source_analysis,
        "excluded_tables": sorted(LEGACY_TABLES - {
            "artist_sources", "source_items", "notification_routes", "notification_deliveries",
            "youtube_channel_monitors", "youtube_channel_videos",
        }),
    }


def build_writer_inventory() -> dict:
    rows = []
    for base in (ROOT / "app", ROOT / "scripts"):
        for path in sorted(base.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            hits = []
            for number, line in enumerate(text.splitlines(), 1):
                if WRITER_PATTERNS.search(line):
                    hits.append(number)
            legacy_mentions = sorted(table for table in LEGACY_TABLES if table in text)
            if hits and (legacy_mentions or "init_db(" in text or "settings.database_url" in text):
                rows.append({"path": path.relative_to(ROOT).as_posix(), "write_or_init_lines": hits,
                             "legacy_tables": legacy_mentions})
    return {
        "generated_at": datetime.now(timezone.utc),
        "rule": "static candidate inventory; each entry requires manual path review before cutover",
        "entries": rows,
    }


def sanitized_routes(legacy: dict, mapping: dict) -> list[dict]:
    source_ids = set(selected_ids(mapping, "x_source", "legacy_source_id"))
    return [{
        "legacy_route_id": row["id"], "legacy_source_id": row["source_id"],
        "selected": row["source_id"] in source_ids,
        "owner_fingerprint": opaque(row["discord_user_id"]),
        "guild_fingerprint": opaque(row["guild_id"]),
        "channel_fingerprint": opaque(row["discord_channel_id"]),
        "active": row["is_active"], "item_type": row["item_type"],
        "delivery_count": row["delivery_count"], "sent_count": row["sent_count"],
    } for row in legacy["routes"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    legacy_url = load_url("LEGACY_DATABASE_URL", ".env")
    catalog_url = load_url("DATABASE_URL", ".env")
    if legacy_url == catalog_url:
        raise RuntimeError("Legacy and catalog URLs resolve to the same configured value")
    args.report_dir.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(legacy_url, connect_timeout=20, row_factory=dict_row) as old_conn:
        with psycopg.connect(catalog_url, connect_timeout=20, row_factory=dict_row) as new_conn:
            configure_read_only(old_conn)
            configure_read_only(new_conn)
            legacy = load_legacy(old_conn)
            catalog = load_catalog(new_conn)
            mapping, conflicts = build_mapping(legacy, catalog)
            manifest = build_manifest(old_conn, new_conn, mapping, legacy)
            conflict_report = {
                "generated_at": datetime.now(timezone.utc),
                "summary": dict(Counter(row["status"] for row in conflicts)),
                "items": conflicts,
            }
            write_json(args.report_dir / "account-mapping.json", mapping)
            write_json(args.report_dir / "selection-manifest.json", manifest)
            write_json(args.report_dir / "conflicts.json", conflict_report)
            write_json(args.report_dir / "writer-inventory.json", build_writer_inventory())
            write_json(args.report_dir / "routes-sanitized.json", sanitized_routes(legacy, mapping))
            print(json.dumps({
                "ok": True,
                "report_dir": args.report_dir.relative_to(ROOT).as_posix(),
                "mapping_summary": mapping["summary"],
                "conflicts": len(conflicts),
                "selected_counts": {name: value["rows"] for name, value in manifest["tables"].items()},
                "checks": manifest["checks"],
            }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
