"""Phase-3 runtime subset migration tests; local PostgreSQL only."""
import importlib.util
from datetime import UTC, datetime
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
        "contract": "runtime-subset-v3",
        "target": identity,
        "baseline_at": "2026-09-21T00:00:00+00:00",
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
            "legacy_job_id": 40, "legacy_archive_ids": [41], "job_type": "youtube_collect",
            "idempotency_key": "youtube_collect:v1:fixture",
            "external_account_id": account, "video_id": None,
            "external_video_id": "abcdefghijk",
            "payload": {"youtube_video_id": "abcdefghijk", "channel_id": "UC1234567890123456789012", "purpose": "archive"},
            "status": "pending", "next_attempt_at": None, "last_error": None,
            "last_checked_at": None, "legacy_wait_count": 0, "attempt_count": 0,
        }],
        "excluded_archives": [],
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
    assert runtime.completed_receipt(database, manifest) == {
        "applied": False, "operation_id": first["operation_id"],
        "counts": manifest["counts"],
    }
    assert database.execute("SELECT count(*) AS n FROM collection_states").fetchone()["n"] == 1
    assert database.execute("SELECT status FROM notification_deliveries").fetchone()["status"] == "sent"
    assert database.execute("SELECT count(*) AS n FROM runtime_legacy_id_map").fetchone()["n"] == 6
    assert database.execute("SELECT target_id FROM runtime_legacy_id_map WHERE source_table='youtube_live_archives'").fetchone()

    second = runtime.apply_plan(database, plan, manifest)
    database.commit()
    assert not second["applied"] and second["operation_id"] == first["operation_id"]
    assert database.execute("SELECT count(*) AS n FROM source_items").fetchone()["n"] == 1


def test_apply_merges_occupied_runtime_without_rewriting_existing_source(database):
    apply(database)
    plan = fixture_plan(database)
    account = plan["collection_states"][0]["external_account_id"]
    database.execute("""INSERT INTO collection_states
      (external_account_id,cursor_value,last_seen_external_id,status,
       lease_owner,lease_expires_at,provider_state)
      VALUES (%s,'90','90','polling','old-worker',clock_timestamp()+interval '5 minutes',
              '{"x_baseline_initialized":true}'::jsonb)""", (account,))
    database.execute("""INSERT INTO source_items
      (external_account_id,external_id,source_url,raw_text,published_at,collected_at)
      VALUES (%s,'post-1','https://x.com/fixture/status/1','existing body',
              '2026-09-21T00:00:00Z','2026-09-21T00:01:00Z')""", (account,))
    database.execute("""INSERT INTO worker_jobs (job_type,idempotency_key,status)
      VALUES ('youtube_poll','existing-poll','pending')""")
    plan["source_items"][0]["published_at"] = datetime(2026, 9, 21, tzinfo=UTC)
    manifest = runtime.public_manifest(plan)
    manifest["approved_for_apply"] = True

    result = runtime.apply_plan(database, plan, manifest)
    database.commit()
    assert result["applied"]
    state = database.execute("""SELECT cursor_value,status,lease_owner,next_poll_at,
                               provider_state FROM collection_states
                               WHERE external_account_id=%s""", (account,)).fetchone()
    assert state["cursor_value"] == "100" and state["status"] == "idle"
    assert state["lease_owner"] is None
    assert state["provider_state"]["legacy_source_ids"] == [10]
    assert database.execute("SELECT raw_text FROM source_items").fetchone()["raw_text"] == "existing body"
    assert database.execute("SELECT count(*) AS n FROM worker_jobs").fetchone()["n"] == 2
    assert database.execute("SELECT count(*) AS n FROM notification_deliveries").fetchone()["n"] == 1


def test_merge_cursor_does_not_regress_target():
    assert runtime.merge_cursor("100", "200") == "200"
    assert runtime.merge_cursor("100", None) == "100"
    with pytest.raises(runtime.RuntimeMigrationError, match="cannot be ordered"):
        runtime.merge_cursor("after-a", "after-b")


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


@pytest.mark.parametrize("has_performances", [False, True])
def test_processed_channel_video_with_pending_archive_is_selected(monkeypatch, has_performances):
    stamp = datetime(2026, 9, 21, tzinfo=UTC)
    x = {"id": 1, "last_seen_external_id": "123", "updated_at": stamp}
    monitor = {"id": 2, "youtube_channel_id": "UC1234567890123456789012",
               "uploads_playlist_id": "UU1234567890123456789012", "next_check_at": stamp,
               "last_checked_at": stamp}
    account = lambda id: {"account_id": id, "collection_enabled": True, "version": 1}
    mapping = {"mappings": [
        {"kind": "x_source", "status": "matched", "legacy_source_id": 1, "account": account(11)},
        {"kind": "youtube_monitor", "status": "matched", "legacy_monitor_id": 2, "account": account(12)},
    ]}
    legacy = {"sources": [x], "monitors": [monitor], "routes": []}
    monkeypatch.setattr(runtime, "verify_target", lambda _: {"catalog_instance_id": "fixture", "schema_version": "catalog-v2"})
    monkeypatch.setattr(runtime.audit, "load_legacy", lambda _: legacy)
    monkeypatch.setattr(runtime.audit, "load_catalog", lambda _: {})
    monkeypatch.setattr(runtime.audit, "build_mapping", lambda *_: (mapping, []))

    class Old:
        def execute(self, sql, params):
            if "FROM source_items i" in sql or "FROM notification_deliveries" in sql:
                return []
            if "FROM youtube_channel_videos" in sql:
                return [dict(id=41, monitor_id=2, youtube_video_id="klmnopqrst0",
                             video_title="Scheduled live", actual_end_at=None,
                             collect_after=None, status="waiting", last_error=None,
                             updated_at=stamp)]
            if "FROM youtube_live_archives" in sql:
                return [dict(id=50, youtube_video_id="abcdefghijk", attempts=3,
                             last_checked_at=stamp, next_check_at=stamp, updated_at=stamp,
                             status="pending", channel_video_id=40, monitor_id=2,
                             channel_status="processed", last_error=None),
                        dict(id=52, youtube_video_id="abcdefghijk", attempts=4,
                             last_checked_at=stamp, next_check_at=stamp, updated_at=stamp,
                             status="pending", channel_video_id=40, monitor_id=2,
                             channel_status="processed", last_error=None),
                        dict(id=51, youtube_video_id="zyxwvutsrqp", attempts=1,
                             last_checked_at=stamp, next_check_at=stamp, updated_at=stamp,
                             status="pending", channel_video_id=None, monitor_id=None,
                             channel_status=None, last_error=None)]
            raise AssertionError(sql)

    class New:
        def execute(self, sql, params):
            if "FROM videos" in sql:
                return [dict(id=90, platform_video_id="abcdefghijk", source_account_id=12,
                             archived_at=None, has_performances=has_performances,
                             archive_state="partial" if has_performances else None, has_cover=False)]
            raise AssertionError(sql)

    plan = runtime.build_plan(Old(), New(), baseline_at=stamp)
    if has_performances:
        assert plan["worker_jobs"] == []
        assert plan["excluded_work"][0]["reason"] == "catalog_archive_already_has_performances"
        assert plan["excluded_work"][0]["legacy_archive_ids"] == [50, 52]
        assert plan["excluded_work"][1]["reason"] == "awaiting_video_end_in_poll_state"
        assert plan["collection_states"][1]["provider_state"]["youtube_pending_video_ids"] == ["klmnopqrst0"]
        assert runtime.public_manifest(plan)["counts"]["worker_jobs"] == 0
        return
    assert len(plan["worker_jobs"]) == 1
    job = plan["worker_jobs"][0]
    assert job["legacy_job_id"] is None and job["legacy_archive_ids"] == [50, 52]
    assert job["video_id"] == 90 and job["payload"]["wait_count"] == 4
    assert job["idempotency_key"].startswith("youtube_collect:v1:12:")
    assert plan["excluded_archives"][0]["legacy_archive_id"] == 51
    assert plan["excluded_work"][0]["reason"] == "awaiting_video_end_in_poll_state"
    manifest = runtime.public_manifest(plan)
    assert manifest["counts"]["worker_jobs"] == 1
    assert manifest["youtube_work"][0]["catalog_video_id"] == 90


def test_failed_apply_rolls_back_and_exact_replay_recovers(database):
    apply(database)
    plan = fixture_plan(database)
    manifest = runtime.public_manifest(plan)
    manifest["approved_for_apply"] = True
    plan["worker_jobs"][0]["job_type"] = "unsupported_job"
    with pytest.raises(Exception):
        with database.transaction():
            runtime.apply_plan(database, plan, manifest)
    assert database.execute("SELECT count(*) FROM runtime_migration_receipts").fetchone()["count"] == 0
    assert database.execute("SELECT count(*) FROM notification_deliveries").fetchone()["count"] == 0
    plan["worker_jobs"][0]["job_type"] = "youtube_collect"
    assert runtime.apply_plan(database, plan, manifest)["applied"]
