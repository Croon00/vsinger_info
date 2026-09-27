"""Starting Spotify collection for catalog artists, on a disposable local PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from test_catalog_migration import local_server, database, apply as apply_schema, row  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("start_spotify_collection", ROOT / "scripts/start_spotify_collection.py")
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


def account(db, sid, *, catalog=True, relationship="owner", n=[0]):
    n[0] += 1
    artist = row(db, "artists", slug=f"a{n[0]}", name_native=f"A{n[0]}", entity_kind="solo", show_in_catalog=catalog)
    acct = row(db, "external_accounts", platform="spotify", platform_id=sid, url=f"https://open.spotify.com/artist/{sid}")
    row(db, "artist_external_accounts", artist_id=artist, account_id=acct, relationship=relationship)
    return acct


def test_start_enables_catalog_owner_accounts_and_enqueues_once(database):
    apply_schema(database)
    wanted = account(database, "a" * 22)
    account(database, "b" * 22, catalog=False)             # hidden artist
    account(database, "c" * 22, relationship="member")      # not the owner
    database.commit()
    info = database.info
    engine = create_engine(f"postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}")
    try:
        with Session(engine) as session:
            preview = start.run(session, write=False)
            assert (preview["accounts"], preview["to_enable"], preview["jobs_to_enqueue"]) == (1, 1, 1)
            session.rollback()
            session.execute(text("DELETE FROM catalog_schema_migrations WHERE version='005'"))
            with pytest.raises(RuntimeError, match="revision 005"):
                start.run(session, write=True)
            session.rollback()
            result = start.run(session, write=True)
            session.commit()
            assert (result["status"], len(result["job_ids"])) == ("committed", 1)
            enabled = dict(session.execute(text("SELECT platform_id, collection_enabled FROM external_accounts")).all())
            assert enabled == {"a" * 22: True, "b" * 22: False, "c" * 22: False}
            job = session.execute(text("SELECT external_account_id, payload, status FROM worker_jobs")).one()
            assert (job[0], job[1]["spotify_artist_id"], job[1]["album_offset"], job[2]) == (wanted, "a" * 22, 0, "pending")
            assert session.execute(text("SELECT count(*) FROM catalog_changes WHERE entity_type='external_accounts'")).scalar() == 1
            again = start.run(session, write=True)
            session.commit()
            assert (again["to_enable"], again["jobs_already_queued"], again["job_ids"]) == (0, 1, result["job_ids"])
            assert session.execute(text("SELECT count(*) FROM worker_jobs")).scalar() == 1
    finally:
        engine.dispose()
