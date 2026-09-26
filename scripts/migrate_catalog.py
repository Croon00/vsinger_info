"""Explicit unified-DB schema migration using the guarded runtime DB URL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "catalog"
REVISION_TABLE = "catalog_schema_migrations"
LOCK_ID = 731064921
# CHECK constraints that later revisions add to revision-001 tables. The 001
# snapshot predates them, so base comparison ignores them and verify() checks them.
LATER_BASE_CONSTRAINTS = {
    ("artists", "artists_name_latin_ascii"): "003",
    ("songs", "songs_title_latin_ascii"): "003",
}
TYPE_NAMES = {
    "BIGINT": "bigint", "INTEGER": "integer", "SMALLINT": "smallint",
    "TEXT": "text", "UUID": "uuid", "BOOLEAN": "boolean", "DATE": "date",
    "TIMESTAMPTZ": "timestamp with time zone", "JSONB": "jsonb",
}


class MigrationError(Exception):
    """Safe, non-sensitive message suitable for CLI output."""


def load_connection() -> str:
    local = dotenv_values(ROOT / ".env")
    if os.environ.get("NEW_DATABASE_URL") or local.get("NEW_DATABASE_URL"):
        raise MigrationError("NEW_DATABASE_URL is retired; configure DATABASE_URL")
    value = os.environ.get("DATABASE_URL") or local.get("DATABASE_URL")
    if not value:
        raise MigrationError("DATABASE_URL is not configured")
    parts = urlsplit(value)
    if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname or not parts.password:
        raise MigrationError("Invalid catalog connection format")
    if not parts.hostname.endswith(".neon.tech"):
        raise MigrationError("CLI only accepts an explicit Neon catalog connection")
    if parse_qs(parts.query).get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
        raise MigrationError("Catalog connection must require TLS")
    return value


def migration_files() -> list[tuple[str, Path]]:
    files = []
    for path in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"):
        version = path.name.partition("_")[0]
        if re.fullmatch(r"[0-9]{3}", version):
            files.append((version, path))
    files.sort()
    if not files or [v for v, _ in files] != [f"{n:03d}" for n in range(1, len(files) + 1)]:
        raise MigrationError("Migration revisions must be contiguous from 001")
    return files


def migration_checksums() -> dict[str, str]:
    return {version: hashlib.sha256(path.read_bytes()).hexdigest()
            for version, path in migration_files()}


def migration_checksum() -> str:
    """Compatibility helper returning the latest revision checksum."""
    return list(migration_checksums().values())[-1]


# Column contract files and the revision that creates their tables.
COLUMN_CONTRACTS = (
    ("001", "columns.json"),
    ("002", "runtime-columns.json"),
    ("004", "song-identity-columns.json"),
)


def expected_columns(*, include_runtime: bool = True, upto: str | None = None) -> dict:
    """Tables expected once revisions <= ``upto`` (default: all) are applied.

    ``include_runtime=False`` keeps the legacy meaning: revision 001 tables only.
    """
    limit = "001" if not include_runtime else upto
    result = {}
    for version, name in COLUMN_CONTRACTS:
        path = MIGRATIONS / name
        if (limit is None or version <= limit) and path.exists():
            result.update(json.loads(path.read_text(encoding="utf-8")))
    return result


def application_tables(conn) -> set[tuple[str, str]]:
    return set(conn.execute("""
        SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p','v','m','f','S')
          AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%'
    """).fetchall())


def table_names(conn) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'")}


def schema_shape(conn) -> dict:
    """Comparable definitions with no data, credentials, host, or object OIDs."""
    result = {}
    queries = {
        "columns": """
            SELECT table_name,column_name,data_type,is_nullable,column_default,
                   is_identity,identity_generation
            FROM information_schema.columns WHERE table_schema='public'
            ORDER BY table_name,ordinal_position
        """,
        "constraints": """
            SELECT c.relname,k.conname,k.contype,pg_get_constraintdef(k.oid,true)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' ORDER BY c.relname,k.conname
        """,
        "indexes": """
            SELECT tablename,indexname,indexdef FROM pg_indexes
            WHERE schemaname='public' ORDER BY tablename,indexname
        """,
        "triggers": """
            SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname
        """,
        "functions": """
            SELECT p.proname,pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)
        """,
    }
    for name, query in queries.items():
        result[name] = [list(r) for r in conn.execute(query)]
    return result


def base_schema_shape(shape: dict) -> dict:
    base_tables = set(expected_columns(include_runtime=False)) | {REVISION_TABLE}
    return {
        name: rows if name == "functions" else [
            row for row in rows
            if row[0] in base_tables
            and not (name == "constraints" and (row[0], row[1]) in LATER_BASE_CONSTRAINTS)
        ]
        for name, rows in shape.items()
    }


def verify_later_constraints(conn, applied: set[str]) -> None:
    found = {tuple(r) for r in conn.execute("""
        SELECT c.relname,k.conname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND k.contype='c'
    """)}
    for key, version in LATER_BASE_CONSTRAINTS.items():
        if (key in found) != (version in applied):
            raise MigrationError("Later revision constraint differs: " + key[1])


def verify_columns(conn, *, include_runtime: bool = True, upto: str | None = None) -> None:
    expected = expected_columns(include_runtime=include_runtime, upto=upto)
    if table_names(conn) != set(expected) | {REVISION_TABLE}:
        raise MigrationError("Catalog table set differs from migration")
    for table, columns in expected.items():
        actual = conn.execute("""
            SELECT column_name,data_type,is_nullable FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position
        """, (table,)).fetchall()
        desired = [(f["name"], TYPE_NAMES[f["type"]], "YES" if f["nullable"] else "NO")
                   for f in columns]
        if actual != desired:
            raise MigrationError("Column contract differs: " + table)


def verify_base_schema(conn) -> None:
    snapshot = MIGRATIONS / "expected-schema.json"
    if snapshot.exists():
        expected = base_schema_shape(json.loads(snapshot.read_text(encoding="utf-8")))
        if base_schema_shape(schema_shape(conn)) != expected:
            raise MigrationError("Base schema definitions differ from revision 001")


def applied_revisions(conn) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT version,checksum FROM public.catalog_schema_migrations ORDER BY version"
    ).fetchall()


def verify_revision_prefix(conn) -> list[tuple[str, str]]:
    applied = applied_revisions(conn)
    expected = list(migration_checksums().items())
    if applied != expected[:len(applied)]:
        raise MigrationError("Migration revision/checksum mismatch")
    return applied


def expected_schema_version() -> str:
    return "catalog-v2" if migration_files()[-1][0] >= "002" else "catalog-v1"


def verify(conn, *, require_empty: bool = False) -> dict:
    revisions = verify_revision_prefix(conn)
    expected_revisions = list(migration_checksums().items())
    if revisions != expected_revisions:
        raise MigrationError("Pending catalog migrations")
    verify_columns(conn)
    verify_base_schema(conn)
    verify_later_constraints(conn, {version for version, _ in revisions})
    identity = conn.execute(
        "SELECT id,schema_version,initial_import_id,initialized_at FROM public.catalog_instance"
    ).fetchall()
    if len(identity) != 1 or identity[0][1] != expected_schema_version():
        raise MigrationError("Invalid catalog identity/version")
    counts = {}
    for table in expected_columns():
        if table == "catalog_instance":
            continue
        counts[table] = conn.execute(
            sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
        ).fetchone()[0]
    if require_empty and (any(counts.values()) or identity[0][2] is not None or identity[0][3] is not None):
        raise MigrationError("Expected catalog with no initial data")
    runtime_count = len(expected_columns(upto="002")) - len(expected_columns(include_runtime=False))
    song_identity_count = len(expected_columns()) - len(expected_columns(upto="003"))
    return {
        "catalog_tables": len(expected_columns(include_runtime=False)),
        "runtime_tables": runtime_count,
        "song_identity_tables": song_identity_count,
        "migration_tables": 1,
        "catalog_instance_id": str(identity[0][0]),
        "schema_version": identity[0][1],
        "initial_data_imported": identity[0][2] is not None,
        "non_identity_row_count": sum(counts.values()),
        "migration_checksums": dict(expected_revisions),
        "verified": True,
    }


def migrate(conn) -> dict:
    """Apply every missing revision in one caller-owned transaction."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    existing = application_tables(conn)
    created = False
    if existing:
        if ("public", REVISION_TABLE) not in existing:
            raise MigrationError("Refusing to alter a non-empty, unmanaged database")
        applied = verify_revision_prefix(conn)
        verify_columns(conn, upto=applied[-1][0] if applied else "001")
        if applied:
            verify_base_schema(conn)
    else:
        objects = conn.execute("""
            SELECT EXISTS(SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                          WHERE n.nspname='public')
              OR EXISTS(SELECT FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                        WHERE n.nspname='public')
        """).fetchone()[0]
        if objects:
            raise MigrationError("Refusing to initialize a database with existing public objects")
        conn.execute("""
            CREATE TABLE public.catalog_schema_migrations (
                version text PRIMARY KEY,
                checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
        """)
        applied = []
        created = True

    already = {version for version, _ in applied}
    applied_now = []
    for version, path in migration_files():
        if version in already:
            continue
        conn.execute(path.read_text(encoding="utf-8"), prepare=False)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        conn.execute(
            "INSERT INTO public.catalog_schema_migrations(version,checksum) VALUES (%s,%s)",
            (version, checksum),
        )
        applied_now.append(version)

    result = verify(conn, require_empty=created)
    result["applied"] = bool(applied_now)
    result["applied_versions"] = applied_now
    return result


def configure_transaction(conn, *, read_only: bool) -> None:
    if read_only:
        conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL search_path=public,pg_catalog")
    conn.execute("SET LOCAL statement_timeout='120s'")
    conn.execute("SET LOCAL lock_timeout='10s'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="Apply pending unified-DB revisions")
    modes.add_argument("--verify", action="store_true", help="Read-only structure/data counts")
    parser.add_argument("--require-empty", action="store_true",
                        help="Verification also requires no initial data")
    args = parser.parse_args()
    try:
        uri = load_connection()
        with psycopg.connect(uri, connect_timeout=20) as conn:
            configure_transaction(conn, read_only=not args.apply)
            if args.apply:
                result = migrate(conn)
            elif args.verify:
                result = verify(conn, require_empty=args.require_empty)
            else:
                result = {"connected": True, "existing_object_count": len(application_tables(conn)),
                          "managed_catalog": REVISION_TABLE in table_names(conn)}
        print(json.dumps(result))
        return 0
    except MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
    except psycopg.Error as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "sqlstate": exc.sqlstate,
                          "next_step": "Run --verify before retrying an uncertain --apply"}))
    except (OSError, ValueError):
        print(json.dumps({"ok": False, "error": "Invalid local catalog settings or migration files"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
