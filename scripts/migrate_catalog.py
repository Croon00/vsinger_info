"""Explicit catalog-only schema migration. Never imports app/runtime or reads DATABASE_URL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "catalog"
VERSION = "001"
REVISION_TABLE = "catalog_schema_migrations"
LOCK_ID = 731064921
TYPE_NAMES = {"INTEGER": "integer", "SMALLINT": "smallint", "TEXT": "text",
              "UUID": "uuid", "BOOLEAN": "boolean", "DATE": "date",
              "TIMESTAMPTZ": "timestamp with time zone", "JSONB": "jsonb"}


class MigrationError(Exception):
    """Safe, non-sensitive message suitable for CLI output."""


def load_connection() -> str:
    value = os.environ.get("NEW_CATALOG_DATABASE_URL")
    if not value:
        path = ROOT / ".env.catalog"
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                key, sep, candidate = line.partition("=")
                if sep and key.strip() == "NEW_CATALOG_DATABASE_URL":
                    value = candidate.strip()
    if not value:
        raise MigrationError("NEW_CATALOG_DATABASE_URL is not configured")
    parts = urlsplit(value)
    if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname or not parts.password:
        raise MigrationError("Invalid catalog connection format")
    if not parts.hostname.endswith(".neon.tech"):
        raise MigrationError("CLI only accepts an explicit Neon catalog connection")
    if parse_qs(parts.query).get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
        raise MigrationError("Catalog connection must require TLS")
    return value


def migration_checksum() -> str:
    return hashlib.sha256((MIGRATIONS / "001_initial.sql").read_bytes()).hexdigest()


def expected_columns() -> dict:
    return json.loads((MIGRATIONS / "columns.json").read_text(encoding="utf-8"))


def application_tables(conn) -> set[tuple[str, str]]:
    return set(conn.execute("""
        SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p','v','m','f','S')
          AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%'
    """).fetchall())


def table_names(conn) -> set[str]:
    return {r[0] for r in conn.execute("""
        SELECT tablename FROM pg_tables WHERE schemaname='public'
    """)}


def schema_shape(conn) -> dict:
    """Comparable catalog definitions; no data, credentials, host or object OIDs."""
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
        """
    }
    for name, query in queries.items():
        result[name] = [list(r) for r in conn.execute(query)]
    return result


def verify_columns(conn) -> None:
    expected = expected_columns()
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


def verify(conn, *, require_empty: bool = False) -> dict:
    verify_columns(conn)
    revisions = conn.execute(
        "SELECT version,checksum FROM public.catalog_schema_migrations ORDER BY version"
    ).fetchall()
    if revisions != [(VERSION, migration_checksum())]:
        raise MigrationError("Migration revision/checksum mismatch")
    snapshot = MIGRATIONS / "expected-schema.json"
    if snapshot.exists() and schema_shape(conn) != json.loads(snapshot.read_text(encoding="utf-8")):
        raise MigrationError("Schema definitions differ from the locally verified migration")
    identity = conn.execute("""
        SELECT id,schema_version,initial_import_id,initialized_at FROM public.catalog_instance
    """).fetchall()
    if len(identity) != 1 or identity[0][1] != "catalog-v1":
        raise MigrationError("Invalid catalog identity/version")
    counts = {}
    for table in expected_columns():
        if table == "catalog_instance":
            continue
        counts[table] = conn.execute(
            sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
        ).fetchone()[0]
    if require_empty and (any(counts.values()) or identity[0][2] is not None or identity[0][3] is not None):
        raise MigrationError("Expected catalog with no initial music import")
    return {"catalog_tables": 31, "migration_tables": 1,
            "catalog_instance_id": str(identity[0][0]), "schema_version": identity[0][1],
            "initial_data_imported": identity[0][2] is not None,
            "non_identity_row_count": sum(counts.values()),
            "migration_checksum": migration_checksum(), "verified": True}


def migrate(conn) -> dict:
    # Caller owns a transaction; the entire DDL + metadata is committed together.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
    existing = application_tables(conn)
    if existing:
        if ("public", REVISION_TABLE) not in existing:
            raise MigrationError("Refusing to alter a non-empty, unmanaged database")
        result = verify(conn)
        result["applied"] = False
        return result
    # Functions/types may exist even when there are no tables.
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
    conn.execute((MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8"), prepare=False)
    conn.execute(
        "INSERT INTO public.catalog_schema_migrations(version,checksum) VALUES (%s,%s)",
        (VERSION, migration_checksum()))
    result = verify(conn, require_empty=True)
    result["applied"] = True
    return result


def configure_transaction(conn, *, read_only: bool) -> None:
    if read_only:
        conn.execute("SET TRANSACTION READ ONLY")
    # SET after connection is compatible with the Neon pooled endpoint.
    conn.execute("SET LOCAL search_path=public,pg_catalog")
    conn.execute("SET LOCAL statement_timeout='120s'")
    conn.execute("SET LOCAL lock_timeout='10s'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="Apply to an empty catalog DB")
    modes.add_argument("--verify", action="store_true", help="Read-only structure/data counts")
    parser.add_argument("--require-empty", action="store_true",
                        help="Verification also requires no initial data")
    args = parser.parse_args()
    try:
        uri = load_connection()
        # Dedicated short-lived migration connection; never touches the runtime engine.
        with psycopg.connect(uri, connect_timeout=20) as conn:
            configure_transaction(conn, read_only=not args.apply)
            if args.apply:
                result = migrate(conn)
            elif args.verify:
                result = verify(conn, require_empty=args.require_empty)
            else:
                result = {"connected": True, "existing_object_count": len(application_tables(conn)),
                          "managed_catalog": REVISION_TABLE in table_names(conn)}
        # Printed only after successful COMMIT/transaction completion.
        print(json.dumps(result))
        return 0
    except MigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
    except psycopg.Error as exc:
        # Database errors can include credentials, hostnames or entire failing rows.
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "sqlstate": exc.sqlstate,
                          "next_step": "Run --verify before retrying an uncertain --apply"}))
    except (OSError, ValueError):
        print(json.dumps({"ok": False, "error": "Invalid local catalog settings or migration files"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
