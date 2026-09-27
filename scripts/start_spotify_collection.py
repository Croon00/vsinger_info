"""Enable Spotify collection for catalog-visible artists and enqueue their first jobs.

Targets are active Spotify accounts linked as ``owner`` to an active ``show_in_catalog``
artist. The preview (default) only reads. ``--apply`` refuses unless catalog revision 005
(ISRC) is applied, then in ONE transaction sets ``collection_enabled=true`` on the targets
that are still disabled (catalog_imports receipt + one catalog_changes row each) and
enqueues one ``spotify_collect`` job per target (``request_run=initial``, album offset 0,
no YouTube matching) through the normal job repository, so account validation and the
idempotency key are the worker's own. Re-running enqueues nothing new.

The deployed worker picks the jobs up only when RUNTIME_CUTOVER_ENABLED and AGENT_ENABLED
are set there; this script does not start any collection itself.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.repositories import worker_jobs  # noqa: E402
from app.schemas.worker_jobs import JobRequest  # noqa: E402

POLICY = "spotify-collection-start-v1"
NAMESPACE = uuid.UUID("0b8e6f1d-4c27-4a95-b3d0-6e2a91c5f7d4")
PAYLOAD = {"request_run": "initial", "link_youtube": False}

_spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts" / "migrate_catalog.py")
migrate_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_catalog)


def targets(session) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT e.id AS account_id, e.platform_id, e.collection_enabled, e.version, min(a.name_native) AS artist
        FROM external_accounts e
        JOIN artist_external_accounts ae ON ae.account_id=e.id AND ae.relationship='owner'
        JOIN artists a ON a.id=ae.artist_id AND a.show_in_catalog AND a.archived_at IS NULL
        WHERE e.platform='spotify' AND e.archived_at IS NULL
        GROUP BY e.id ORDER BY e.id""")).mappings()]


def request(target: dict) -> JobRequest:
    return JobRequest(job_type="spotify_collect", external_account_id=target["account_id"],
                      payload={"spotify_artist_id": target["platform_id"], **PAYLOAD})


def run(session, *, write: bool) -> dict:
    identity = session.execute(text("SELECT id::text, schema_version FROM catalog_instance")).one()
    revisions = {r[0] for r in session.execute(text("SELECT version FROM catalog_schema_migrations"))}
    if identity[1] != "catalog-v2":
        raise RuntimeError("Unexpected catalog schema")
    if write:
        session.execute(text("SELECT pg_advisory_xact_lock(731064925)"))
    rows = targets(session)
    keys = {t["account_id"]: request(t).key() for t in rows}
    queued = {r[0] for r in session.execute(text("""SELECT external_account_id FROM worker_jobs
        WHERE job_type='spotify_collect' AND idempotency_key = ANY(:keys)"""), {"keys": list(keys.values())})}
    disabled = [t for t in rows if not t["collection_enabled"]]
    summary = {"accounts": len(rows), "to_enable": len(disabled), "already_enabled": len(rows) - len(disabled),
               "jobs_to_enqueue": sum(t["account_id"] not in queued for t in rows),
               "jobs_already_queued": len(queued), "revision_005": "005" in revisions}
    if not write:
        return {"status": "preview", **summary, "artists": [t["artist"] for t in rows]}
    if "005" not in revisions:
        raise RuntimeError("Apply catalog revision 005 (ISRC) before starting Spotify collection")
    changes = []
    for t in disabled:
        after = session.execute(text("""UPDATE external_accounts SET collection_enabled=true
            WHERE id=:id AND version=:version AND NOT collection_enabled AND archived_at IS NULL
            RETURNING to_jsonb(external_accounts)"""), {"id": t["account_id"], "version": t["version"]}).scalar_one_or_none()
        if after is None:
            raise RuntimeError(f"Account {t['account_id']} changed since preview; re-run")
        changes.append((t["account_id"], after))
    jobs = [worker_jobs.enqueue(session, request(t)) for t in rows]
    digest = hashlib.sha256(json.dumps({"policy": POLICY, "accounts": [c[0] for c in changes]},
                                       sort_keys=True).encode()).hexdigest()
    if changes:
        import_id = session.execute(text("""INSERT INTO catalog_imports(operation_id,catalog_instance_id,manifest_hash,
                source_kind,result_mapping,result_summary)
            VALUES (:op,:catalog,:hash,'manual',CAST(:mapping AS jsonb),CAST(:summary AS jsonb)) RETURNING id"""),
            {"op": str(uuid.uuid5(NAMESPACE, identity[0] + ":" + digest)), "catalog": identity[0], "hash": digest,
             "mapping": json.dumps([{"entity_type": "external_accounts", "id": c[0]} for c in changes]),
             "summary": json.dumps({"kind": POLICY, **summary, "jobs": jobs})}).scalar_one()
        for account_id, after in changes:
            session.execute(text("""INSERT INTO catalog_changes(import_id,entity_type,entity_id,action,before_data,after_data,provenance)
                VALUES (:import,'external_accounts',:id,'update',CAST(:before AS jsonb),CAST(:after AS jsonb),CAST(:prov AS jsonb))"""),
                {"import": import_id, "id": account_id, "before": json.dumps({"collection_enabled": False}),
                 "after": json.dumps({"collection_enabled": True, "version": after["version"]}),
                 "prov": json.dumps({"policy": POLICY, "reason": "user approved Spotify collection for catalog artists"})})
    return {"status": "committed", **summary, "job_ids": jobs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = migrate_catalog.load_connection().replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1)
    engine = create_engine(url, connect_args={"connect_timeout": 20})
    try:
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY" if not args.apply else "SET LOCAL lock_timeout='10s'"))
            result = run(session, write=args.apply)
            if args.apply:
                session.commit()
            else:
                session.rollback()
    finally:
        engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
