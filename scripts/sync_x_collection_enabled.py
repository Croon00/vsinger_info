"""Copy legacy X source activation to matching catalog external accounts.

The legacy database is always opened read-only. Exact platform_id matches are
preferred; a unique normalized handle match is accepted when no exact match
exists. The catalog is changed only with --apply, using an optimistic version
check and catalog import/change receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPERATION_ID = uuid.UUID("fda385a5-80f0-59cd-b818-c662f4c15d47")
LEGACY_X_HANDLE_ALIASES = {
    "imi_rkmusic": "imi0131",
    "honkthehorn": "honkthehorn_",
    "haru_saruhi": "harusaruhi",
}
LEGACY_X_EXCLUDED_SOURCE_IDS = {12, 72, 73}


def load_url(variable: str, filename: str) -> str:
    value = (dotenv_values(ROOT / filename).get(variable) or "").strip()
    if not value:
        raise RuntimeError(f"{variable} is not configured in {filename}")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError(f"{variable} is not a PostgreSQL URL")
    return value


def normalize_handle(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if "://" in candidate:
        candidate = urlsplit(candidate).path.strip("/").split("/")[0]
    return candidate.lstrip("@").casefold() or None


def setup(conn, *, read_only: bool) -> None:
    if read_only:
        conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL search_path=public,pg_catalog")
    conn.execute("SET LOCAL statement_timeout='120s'")
    conn.execute("SET LOCAL lock_timeout='10s'")


def build_plan(old_conn, new_conn) -> tuple[dict, list[dict]]:
    sources = old_conn.execute(
        """SELECT id,external_user_id,value,is_active
           FROM artist_sources
           WHERE source_type='x' AND NOT (id=ANY(%s)) ORDER BY id""",
        (list(LEGACY_X_EXCLUDED_SOURCE_IDS),),
    ).fetchall()
    accounts = new_conn.execute(
        """SELECT id,platform_id,handle,url,collection_enabled,archived_at,version
           FROM external_accounts WHERE platform='x' ORDER BY id"""
    ).fetchall()
    by_platform_id: dict[str, list[tuple]] = defaultdict(list)
    by_handle: dict[str, list[tuple]] = defaultdict(list)
    for account in accounts:
        if account[1]:
            by_platform_id[str(account[1])].append(account)
        for handle in {normalize_handle(account[2]), normalize_handle(account[3])} - {None}:
            by_handle[handle].append(account)

    assignments: dict[int, list[dict]] = defaultdict(list)
    unresolved = []
    for source_id, platform_id, handle, active in sources:
        exact = by_platform_id.get(str(platform_id), []) if platform_id else []
        normalized = normalize_handle(handle)
        lookup_handle = LEGACY_X_HANDLE_ALIASES.get(normalized, normalized)
        candidates = exact if exact else by_handle.get(lookup_handle, [])
        evidence = "platform_id" if exact else "handle"
        if len(candidates) != 1:
            unresolved.append({
                "legacy_source_id": source_id,
                "reason": "missing_account" if not candidates else "ambiguous_account",
                "candidate_count": len(candidates),
            })
            continue
        account = candidates[0]
        assignments[int(account[0])].append({
            "legacy_source_id": int(source_id),
            "desired": bool(active),
            "evidence": evidence,
            "legacy_platform_id_differs": bool(
                evidence == "handle" and platform_id
                and str(platform_id) != str(account[1] or "")
            ),
        })

    plan = []
    for account in accounts:
        account_id = int(account[0])
        matched = assignments.get(account_id, [])
        if not matched:
            continue
        desired_values = {item["desired"] for item in matched}
        if len(desired_values) != 1:
            unresolved.append({
                "account_id": account_id,
                "reason": "legacy_activation_conflict",
                "legacy_source_ids": [item["legacy_source_id"] for item in matched],
            })
            continue
        if account[5] is not None:
            unresolved.append({
                "account_id": account_id,
                "reason": "catalog_account_archived",
                "legacy_source_ids": [item["legacy_source_id"] for item in matched],
            })
            continue
        plan.append({
            "account_id": account_id,
            "expected_version": int(account[6]),
            "before": bool(account[4]),
            "desired": desired_values.pop(),
            "legacy_source_ids": [item["legacy_source_id"] for item in matched],
            "evidence": sorted({item["evidence"] for item in matched}),
            "legacy_platform_id_differs": any(
                item["legacy_platform_id_differs"] for item in matched
            ),
        })
    catalog_id = str(new_conn.execute(
        "SELECT id FROM catalog_instance"
    ).fetchone()[0])
    payload = {
        "catalog_id": catalog_id,
        "policy": "exact_platform_id_or_unique_normalized_handle",
        "accounts": plan,
        "unresolved": unresolved,
    }
    return payload, unresolved


def manifest_hash(plan: dict) -> str:
    return hashlib.sha256(
        json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def apply_plan(conn, plan: dict, digest: str, operation_id: uuid.UUID) -> dict:
    identity = conn.execute(
        "SELECT id FROM catalog_instance FOR UPDATE"
    ).fetchone()[0]
    if str(identity) != plan["catalog_id"]:
        raise RuntimeError("Catalog identity changed after preview")
    existing = conn.execute(
        "SELECT manifest_hash,result_summary FROM catalog_imports WHERE operation_id=%s",
        (operation_id,),
    ).fetchone()
    if existing:
        return {
            "already_applied": True,
            "recorded_manifest_hash": existing[0],
            **existing[1],
        }

    changed = []
    unchanged = 0
    for item in plan["accounts"]:
        before = conn.execute(
            "SELECT to_jsonb(e) FROM external_accounts e WHERE id=%s FOR UPDATE",
            (item["account_id"],),
        ).fetchone()
        if not before:
            raise RuntimeError("Catalog account disappeared after preview")
        before_data = before[0]
        if int(before_data["version"]) != item["expected_version"]:
            raise RuntimeError("Catalog account version changed after preview")
        if bool(before_data["collection_enabled"]) == item["desired"]:
            unchanged += 1
            continue
        after_data = conn.execute(
            """UPDATE external_accounts
               SET collection_enabled=%s,version=version+1,updated_at=clock_timestamp()
               WHERE id=%s AND version=%s RETURNING to_jsonb(external_accounts)""",
            (item["desired"], item["account_id"], item["expected_version"]),
        ).fetchone()
        if not after_data:
            raise RuntimeError("Optimistic account update failed")
        changed.append((item, before_data, after_data[0]))

    mapping = [{
        "entity_type": "external_accounts",
        "entity_id": item["account_id"],
        "version": after["version"],
    } for item, _, after in changed]
    summary = {
        "matched_accounts": len(plan["accounts"]),
        "enabled_count": sum(item["desired"] for item in plan["accounts"]),
        "disabled_count": sum(not item["desired"] for item in plan["accounts"]),
        "updated_count": len(changed),
        "unchanged_count": unchanged,
        "unresolved_source_count": len(plan["unresolved"]),
    }
    receipt_id = conn.execute(
        """INSERT INTO catalog_imports
           (operation_id,catalog_instance_id,manifest_hash,source_kind,result_mapping,result_summary)
           VALUES (%s,%s,%s,'correction',%s,%s) RETURNING id""",
        (operation_id, identity, digest, Jsonb(mapping), Jsonb(summary)),
    ).fetchone()[0]
    for item, before, after in changed:
        conn.execute(
            """INSERT INTO catalog_changes
               (import_id,entity_type,entity_id,action,before_data,after_data,provenance)
               VALUES (%s,'external_accounts',%s,'update',%s,%s,%s)""",
            (receipt_id, item["account_id"], Jsonb(before), Jsonb(after), Jsonb({
                "policy": plan["policy"],
                "legacy_source_ids": item["legacy_source_ids"],
                "match_evidence": item["evidence"],
                "legacy_platform_id_differs": item["legacy_platform_id_differs"],
            })),
        )
    return {"already_applied": False, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operation-id", type=uuid.UUID, default=DEFAULT_OPERATION_ID)
    args = parser.parse_args()
    legacy_url = load_url("DATABASE_URL", ".env")
    catalog_url = load_url("NEW_DATABASE_URL", ".env.catalog")
    if legacy_url == catalog_url:
        raise RuntimeError("Legacy and catalog URLs resolve to the same configured value")
    with psycopg.connect(legacy_url, connect_timeout=20) as old_conn:
        setup(old_conn, read_only=True)
        with psycopg.connect(catalog_url, connect_timeout=20) as new_conn:
            setup(new_conn, read_only=not args.apply)
            plan, unresolved = build_plan(old_conn, new_conn)
            digest = manifest_hash(plan)
            preview = {
                "matched_accounts": len(plan["accounts"]),
                "enable": sum(item["desired"] for item in plan["accounts"]),
                "disable": sum(not item["desired"] for item in plan["accounts"]),
                "would_change": sum(item["before"] != item["desired"] for item in plan["accounts"]),
                "unchanged": sum(item["before"] == item["desired"] for item in plan["accounts"]),
                "platform_id_matches": sum("platform_id" in item["evidence"] for item in plan["accounts"]),
                "handle_matches": sum("handle" in item["evidence"] for item in plan["accounts"]),
                "unresolved_sources": len(unresolved),
                "manifest_hash": digest,
            }
            if not args.apply:
                print(json.dumps({"mode": "preview", **preview}))
                return 0
            result = apply_plan(new_conn, plan, digest, args.operation_id)
            print(json.dumps({"mode": "apply", **preview, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
