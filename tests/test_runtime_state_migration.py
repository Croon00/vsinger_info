"""Phase-3 runtime subset migration tests; local PostgreSQL only."""
import importlib.util
from pathlib import Path

import pytest
from psycopg.rows import dict_row

from test_catalog_migration import ROOT, apply, database, local_server, row

spec = importlib.util.spec_from_file_location(
    "migrate_runtime_state", ROOT / "scripts" / "migrate_runtime_state.py"
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def fixture_plan(conn):
    account = row(conn, "external_accounts", platform="x", platform_id="42",
                  handle="fixture", url="https://x.com/fixture", collection_enabled=True)
    conn.row_factory = dict_row
    identity = runtime.verify_target(conn)
    plan = {
        "contract": "runtime-subset-v1",
        "target": identity,
        "account_versions": {str(account): 1},
        "collection_states": [{
            "external_account_id": account, "cursor_value": "100",
            "last_seen_external_id": "100", "status": "idle",
            "next_poll_at": None, "last_polled_at": None,
            "provider_state": {"legacy_source_ids": [10],
                               "selected_cursor_source_id": 10},
        }],
        "routes": [{
            "external_account_id": account, "guild_id": "200", "channel_id": "300",
            "owner_discord_user_id": "100", "is_active": True,
            "legacy_route_ids": [20],
        }],
        "source_items": [{
            "external_account_id": account, "external_id": "post-1",
            "source_url": "https://x.com/fixture/status/1", "raw_text": "fixture",
            "published_at": "2026-09-21T00:00:00Z",
            "collected_at": "2026-09-21T00:01:00Z",
        }],
        "deliveries": [{
            "legacy_delivery_id": 30, "legacy_route_id": 20,
            "item_key": (account, "post-1"), "discord_message_id": "400",
            "delivered_at": "2026-09-21T00:02:00Z",
        }],
        "worker_jobs": [{
            "legacy_job_id": 40, "job_type": "youtube_collect",
            "idempotency_key": "legacy:youtube_channel_videos:40",
            "external_account_id": account, "video_id": None,
            "payload": {"youtube_video_id": "abcdefghijk", "actual_end_at": None},
            "status": "pending", "next_attempt_at": None, "last_error": None,
        }],
        "legacy_item_keys": {"50": [account, "post-1"]},
        "route_keys": {"20": [account, "200", "300"]},
        "source_snapshot_hash": "a" * 64,
    }
    return plan


def test_apply_is_atomic_audited_and_idempotent(database):
    apply(database)
    plan = fixture_plan(database)
    manifest = runtime.public_manifest(plan)
    manifest["approved_for_apply"] = True

    first = runtime.apply_plan(database, plan, manifest)
    database.commit()
    assert first["applied"]
    assert database.execute("SELECT count(*) AS n FROM collection_states").fetchone()["n"] == 1
    assert database.execute("SELECT status FROM notification_deliveries").fetchone()["status"] == "sent"
    assert database.execute("SELECT count(*) AS n FROM runtime_legacy_id_map").fetchone()["n"] == 5

    second = runtime.apply_plan(database, plan, manifest)
    database.commit()
    assert not second["applied"] and second["operation_id"] == first["operation_id"]
    assert database.execute("SELECT count(*) AS n FROM source_items").fetchone()["n"] == 1


def test_apply_rejects_unapproved_or_changed_manifest(database):
    apply(database)
    plan = fixture_plan(database)
    manifest = runtime.public_manifest(plan)
    with pytest.raises(runtime.RuntimeMigrationError, match="approved_for_apply"):
        runtime.apply_plan(database, plan, manifest)
    manifest["approved_for_apply"] = True
    manifest["counts"]["source_items"] = 99
    with pytest.raises(runtime.RuntimeMigrationError, match="Exact dry-run"):
        runtime.apply_plan(database, plan, manifest)
