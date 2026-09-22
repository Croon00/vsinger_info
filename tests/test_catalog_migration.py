"""Local PostgreSQL-only catalog migration tests; never loads .env or reaches Neon."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import uuid

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("migrate_catalog", ROOT / "scripts/migrate_catalog.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture(scope="module")
def local_server():
    binaries = Path(os.environ.get("POSTGRES_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
    initdb, pgctl = binaries / "initdb.exe", binaries / "pg_ctl.exe"
    if not initdb.exists() or not pgctl.exists():
        pytest.skip("Local PostgreSQL binaries required; no remote fallback")
    base = ROOT / ".tmp"
    base.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="catalog-pg-", dir=base))
    data = directory / "data"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    def run(args):
        # pg_ctl's child can inherit Windows pipe handles; use a file, not PIPE.
        helper_log = directory / "helper.log"
        with helper_log.open("ab") as output:
            completed = subprocess.run([str(a) for a in args], stdout=output,
                                       stderr=subprocess.STDOUT, timeout=60, creationflags=flags)
        if completed.returncode:
            pytest.fail("Local PostgreSQL helper failed: " +
                        helper_log.read_text(encoding="utf-8", errors="replace"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    run([initdb, "-D", data, "-U", "catalog_test", "-A", "trust",
         "--encoding=UTF8", "--locale=C"])
    started = False
    try:
        run([pgctl, "-D", data, "-l", directory / "postgres.log", "-w", "-t", "30",
             "-o", f"-h 127.0.0.1 -p {port} -F", "start"])
        started = True
        yield f"host=127.0.0.1 port={port} dbname=postgres user=catalog_test"
    finally:
        if started:
            run([pgctl, "-D", data, "-m", "fast", "-w", "stop"])
        # Keep local logs available; never delete arbitrary/derived external directories.


@pytest.fixture
def database(local_server):
    name = "catalog_" + uuid.uuid4().hex
    with psycopg.connect(local_server, autocommit=True) as control:
        control.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(name)))
    conn = psycopg.connect(local_server.replace("dbname=postgres", "dbname=" + name))
    try:
        yield conn
    finally:
        conn.close()
        with psycopg.connect(local_server, autocommit=True) as control:
            control.execute(psycopg.sql.SQL("DROP DATABASE {}").format(psycopg.sql.Identifier(name)))


def apply(conn):
    migration.configure_transaction(conn, read_only=False)
    result = migration.migrate(conn)
    conn.commit()
    return result


def row(conn, table, **values):
    cols = list(values)
    query = psycopg.sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) RETURNING id").format(
        psycopg.sql.Identifier(table),
        psycopg.sql.SQL(",").join(map(psycopg.sql.Identifier, cols)),
        psycopg.sql.SQL(",").join([psycopg.sql.Placeholder()] * len(cols)))
    return conn.execute(query, list(values.values())).fetchone()[0]


def artist(conn, label="one", **extra):
    return row(conn, "artists", slug=label, name_native="Test artist", entity_kind="solo", **extra)


def reject(conn, code, callback):
    with pytest.raises(psycopg.Error) as error:
        with conn.transaction():
            callback()
    assert error.value.sqlstate == code


def test_schema_contract_and_empty_initial_state(database):
    report = apply(database)
    assert report["applied"] and report["non_identity_row_count"] == 0
    assert report["applied_versions"] == ["001", "002"]
    assert report["schema_version"] == "catalog-v2"
    assert not report["initial_data_imported"]
    assert len(migration.table_names(database)) == 42
    second = migration.migrate(database)
    assert not second["applied"]
    assert second["catalog_instance_id"] == report["catalog_instance_id"]
    expected = migration.expected_columns()
    assert len(expected) == 41
    assert {"title_latin", "language_code"} <= {f["name"] for f in expected["songs"]}
    assert "karaoke_numbers" in expected
    assert not {"artist_links", "song_credits", "recording_credits", "legacy_entity_map"} & expected.keys()
    # Opt-in snapshot is generated ONLY from a tested local instance, never from Neon.
    if os.environ.get("CATALOG_EXPORT_LOCAL_SCHEMA") == "1":
        (migration.MIGRATIONS / "expected-schema.json").write_text(
            json.dumps(migration.base_schema_shape(migration.schema_shape(database)), indent=2) + "\n",
            encoding="utf-8")


def test_upgrade_from_001_preserves_catalog_rows(database):
    migration.configure_transaction(database, read_only=False)
    database.execute("""
        CREATE TABLE public.catalog_schema_migrations (
          version text PRIMARY KEY,
          checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
          applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    database.execute((migration.MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8"),
                     prepare=False)
    database.execute(
        "INSERT INTO catalog_schema_migrations(version,checksum) VALUES ('001',%s)",
        (migration.migration_checksums()["001"],),
    )
    account = row(database, "external_accounts", platform="x", platform_id="123",
                  handle="fixture", url="https://x.com/fixture", collection_enabled=True)
    database.commit()

    report = apply(database)
    assert report["applied_versions"] == ["002"]
    assert database.execute(
        "SELECT platform_id,collection_enabled FROM external_accounts WHERE id=%s", (account,)
    ).fetchone() == ("123", True)
    assert database.execute("SELECT schema_version FROM catalog_instance").fetchone()[0] == "catalog-v2"


def test_runtime_fk_dedup_delivery_and_job_contracts(database):
    apply(database)
    account = row(database, "external_accounts", platform="x", platform_id="42",
                  handle="fixture", url="https://x.com/fixture", collection_enabled=True)
    database.execute("INSERT INTO discord_users(discord_user_id) VALUES ('100')")
    database.execute("""
        INSERT INTO discord_guilds(guild_id,owner_discord_user_id) VALUES ('200','100');
        INSERT INTO discord_channels(channel_id,guild_id) VALUES ('300','200')
    """, prepare=False)
    database.execute("INSERT INTO collection_states(external_account_id,cursor_value) VALUES (%s,'41')",
                     (account,))
    item = row(database, "source_items", external_account_id=account, external_id="post-1",
               source_url="https://x.com/fixture/status/1", raw_text="fixture",
               published_at="2026-09-21T00:00:00Z")
    reject(database, "23505", lambda: row(database, "source_items",
        external_account_id=account, external_id="post-1",
        source_url="https://x.com/fixture/status/1", raw_text="duplicate",
        published_at="2026-09-21T00:00:00Z"))
    route = row(database, "notification_routes", external_account_id=account,
                guild_id="200", channel_id="300", owner_discord_user_id="100")
    delivery = row(database, "notification_deliveries", route_id=route,
                   source_item_id=item, status="pending")
    reject(database, "23505", lambda: row(database, "notification_deliveries",
        route_id=route, source_item_id=item, status="pending"))
    reject(database, "23514", lambda: database.execute(
        "UPDATE notification_deliveries SET status='sent' WHERE id=%s", (delivery,)))
    database.execute("""
        UPDATE notification_deliveries
        SET status='sent', delivered_at=clock_timestamp(), discord_message_id='400'
        WHERE id=%s
    """, (delivery,))
    job = row(database, "worker_jobs", job_type="x_poll", idempotency_key="x:42:1",
              external_account_id=account)
    reject(database, "23505", lambda: row(database, "worker_jobs",
        job_type="x_poll", idempotency_key="x:42:1", external_account_id=account))
    assert job and database.execute(
        "SELECT version FROM notification_deliveries WHERE id=%s", (delivery,)
    ).fetchone()[0] == 2


def test_runtime_guild_ownership_and_receipts(database):
    apply(database)
    account = row(database, "external_accounts", platform="x", platform_id="99",
                  handle="other", url="https://x.com/other")
    database.execute("INSERT INTO discord_guilds(guild_id) VALUES ('500'),('501')")
    database.execute("INSERT INTO discord_channels(channel_id,guild_id) VALUES ('600','500')")
    reject(database, "23503", lambda: row(database, "notification_routes",
        external_account_id=account, guild_id="501", channel_id="600"))
    identity = database.execute("SELECT id FROM catalog_instance").fetchone()[0]
    receipt = row(database, "runtime_migration_receipts", operation_id=uuid.uuid4(),
                  catalog_instance_id=identity, source_fingerprint="a" * 64,
                  manifest_hash="b" * 64)
    mapping = row(database, "runtime_legacy_id_map", receipt_id=receipt,
                  source_table="artist_sources", legacy_id="10",
                  target_table="collection_states", target_id=str(account),
                  selection_reason="matched platform_id")
    reject(database, "23514", lambda: database.execute(
        "UPDATE runtime_legacy_id_map SET selection_reason='changed' WHERE id=%s", (mapping,)))


def test_unified_connection_guard(database, monkeypatch):
    apply(database)
    from app.core.config import settings
    from app.db.catalog_session import CatalogIdentityError, verify_catalog_identity

    info = database.info
    engine = create_engine(
        f"postgresql+psycopg://catalog_test@127.0.0.1:{info.port}/{info.dbname}"
    )
    monkeypatch.setattr(settings, "catalog_schema_version", "catalog-v2")
    monkeypatch.setattr(settings, "new_database_instance_id", None)
    try:
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            instance_id = verify_catalog_identity(session)
        monkeypatch.setattr(settings, "new_database_instance_id", str(uuid.uuid4()))
        with Session(engine) as session, pytest.raises(CatalogIdentityError, match="instance identity"):
            session.execute(text("SET TRANSACTION READ ONLY"))
            verify_catalog_identity(session)
        assert instance_id
    finally:
        engine.dispose()


def test_legacy_init_is_blocked_on_unified_database(database, monkeypatch):
    apply(database)
    from app.core.config import settings
    from app.core.db import init_db

    info = database.info
    monkeypatch.setattr(
        settings,
        "database_url",
        f"postgresql://catalog_test@127.0.0.1:{info.port}/{info.dbname}",
    )
    with pytest.raises(RuntimeError, match="Legacy init_db is blocked"):
        init_db()


def test_reject_existing_unmanaged_database(database):
    database.execute("CREATE TABLE public.existing_service (id integer)")
    with pytest.raises(migration.MigrationError, match="non-empty"):
        migration.migrate(database)
    assert migration.table_names(database) == {"existing_service"}


def test_invalid_migration_rolls_back_all_ddl(database, monkeypatch, tmp_path):
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "001_initial.sql").write_text("CREATE TABLE should_rollback(id integer); SELECT 1/0;")
    monkeypatch.setattr(migration, "MIGRATIONS", folder)
    with pytest.raises(psycopg.errors.DivisionByZero):
        with database.transaction():
            migration.migrate(database)
    assert not migration.application_tables(database)


def test_song_identity_collaboration_and_karaoke(database):
    apply(database)
    a, b = artist(database, "a"), artist(database, "b")
    song1 = row(database, "songs", title_native="Same title", title_latin="Title", language_code="ja")
    song2 = row(database, "songs", title_native="Same title")
    assert song1 != song2
    row(database, "song_artists", song_id=song1, artist_id=a)
    row(database, "song_artists", song_id=song1, artist_id=b)
    reject(database, "23505", lambda: row(database, "song_artists", song_id=song1, artist_id=a))
    reject(database, "23503", lambda: row(database, "song_artists", song_id=song1, artist_id=999999))
    row(database, "karaoke_numbers", song_id=song1, provider="tj", number="00123")
    row(database, "karaoke_numbers", song_id=song1, provider="ky", number="00123")
    reject(database, "23505", lambda: row(database, "karaoke_numbers", song_id=song1, provider="tj", number="00123"))
    reject(database, "23001", lambda: database.execute("DELETE FROM artists WHERE id=%s", (a,)))


def test_date_precision_and_partial_release_dates(database):
    apply(database)
    event = row(database, "concerts", title="Date only", event_format="onsite",
                time_precision="date", event_date="2026-09-20", status="scheduled", city="Tokyo")
    assert database.execute("SELECT starts_at FROM concerts WHERE id=%s", (event,)).fetchone()[0] is None
    row(database, "concerts", title="Exact", event_format="hybrid", time_precision="datetime",
        event_date="2026-09-20", starts_at="2026-09-20T18:00:00+09:00", timezone_name="Asia/Tokyo", status="scheduled")
    reject(database, "23514", lambda: row(database, "concerts", title="Wrong date",
        event_format="onsite", time_precision="datetime", event_date="2026-09-19",
        starts_at="2026-09-20T18:00:00+09:00", timezone_name="Asia/Tokyo", status="scheduled"))
    reject(database, "23514", lambda: row(database, "concerts", title="Unknown zone",
        event_format="onsite", time_precision="datetime", event_date="2026-09-20",
        starts_at="2026-09-20T18:00:00+09:00", timezone_name="not/a-zone", status="scheduled"))
    row(database, "albums", title_native="Year only", album_type="album", release_year=2026)
    reject(database, "23514", lambda: row(database, "albums", title_native="Invalid date",
        album_type="album", release_year=2026, release_month=2, release_day=30))
    artist(database, "leap", birthday_month=2, birthday_day=29)
    reject(database, "23514", lambda: artist(database, "bad", birthday_month=2, birthday_day=30))


def test_video_setlist_unmatched_and_versions(database):
    apply(database)
    singer = artist(database)
    video = row(database, "videos", platform="youtube", platform_video_id="abcdefghijk", title="Archive")
    reject(database, "23505", lambda: row(database, "videos", platform="youtube",
        platform_video_id="abcdefghijk", title="Duplicate"))
    archive = row(database, "live_archives", video_id=video)
    performance = row(database, "performances", archive_id=archive, ordinal=1,
                      start_seconds=930, raw_title="Unmatched")
    assert database.execute("SELECT song_id FROM performances WHERE id=%s", (performance,)).fetchone()[0] is None
    old = database.execute("SELECT version FROM live_archives WHERE id=%s", (archive,)).fetchone()[0]
    row(database, "performance_artists", performance_id=performance, artist_id=singer, role="lead")
    assert database.execute("SELECT version FROM performances WHERE id=%s", (performance,)).fetchone()[0] == 2
    assert database.execute("SELECT version FROM live_archives WHERE id=%s", (archive,)).fetchone()[0] > old
    reject(database, "23514", lambda: row(database, "performances", archive_id=archive,
        ordinal=2, start_seconds=20, end_seconds=10, raw_title="Bad timestamp"))


def test_shared_recording_album_positions_and_lyrics(database):
    apply(database)
    recording = row(database, "recordings", title_native="Recording")
    album1 = row(database, "albums", title_native="Single", album_type="single")
    album2 = row(database, "albums", title_native="Album", album_type="album")
    row(database, "album_tracks", album_id=album1, recording_id=recording, track_number=1)
    row(database, "album_tracks", album_id=album2, recording_id=recording, track_number=2)
    reject(database, "23505", lambda: row(database, "album_tracks",
        album_id=album2, recording_id=recording, track_number=2))
    row(database, "recording_lyrics", recording_id=recording, original_lyrics="Synthetic test text")
    reject(database, "23505", lambda: row(database, "recording_lyrics",
        recording_id=recording, original_lyrics="Duplicate"))


def test_history_receipts_and_link_settings(database):
    apply(database)
    identity = database.execute("SELECT id FROM catalog_instance").fetchone()[0]
    operation = uuid.uuid4()
    receipt = row(database, "catalog_imports", operation_id=operation,
                  catalog_instance_id=identity, manifest_hash="a" * 64, source_kind="manual")
    reject(database, "23505", lambda: row(database, "catalog_imports",
        operation_id=operation, catalog_instance_id=identity, manifest_hash="a" * 64, source_kind="manual"))
    reject(database, "23514", lambda: database.execute("DELETE FROM catalog_imports WHERE id=%s", (receipt,)))
    account = row(database, "external_accounts", platform="website", url="https://example.com")
    reject(database, "23514", lambda: database.execute(
        "UPDATE external_accounts SET collection_enabled=true WHERE id=%s", (account,)))
    singer = artist(database)
    row(database, "artist_external_accounts", artist_id=singer, account_id=account,
        relationship="owner", label="Official", position=0)
    assert not database.execute("SELECT collection_enabled FROM external_accounts").fetchone()[0]


def test_checksum_and_definition_drift_are_rejected(database):
    apply(database)
    database.execute("UPDATE catalog_schema_migrations SET checksum=%s", ("b" * 64,))
    with pytest.raises(migration.MigrationError, match="checksum"):
        migration.migrate(database)
    database.rollback()
    database.execute("ALTER TABLE songs ADD COLUMN accidental text")
    with pytest.raises(migration.MigrationError, match="Column contract"):
        migration.migrate(database)
