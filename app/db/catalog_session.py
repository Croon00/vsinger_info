"""Guarded pool for the unified DB; never falls back to the legacy DATABASE_URL."""
from functools import lru_cache
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings

REQUIRED_REVISIONS = ("001", "002")


class CatalogIdentityError(RuntimeError):
    """The connection does not point at the expected managed unified database."""


def catalog_url() -> str:
    return settings.new_database_url or ""


@lru_cache(maxsize=4)
def catalog_engine(url: str):
    normalized = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )
    return create_engine(
        normalized,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=15,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
        hide_parameters=True,
    )


def verify_catalog_identity(session: Session) -> str:
    try:
        revisions = tuple(session.execute(text(
            "SELECT version FROM public.catalog_schema_migrations ORDER BY version"
        )).scalars())
        identity = session.execute(text(
            "SELECT id::text,schema_version FROM public.catalog_instance"
        )).one()
    except SQLAlchemyError as exc:
        raise CatalogIdentityError("Unified DB schema identity is unavailable") from exc
    if revisions != REQUIRED_REVISIONS:
        raise CatalogIdentityError("Unified DB migration revision mismatch")
    if identity.schema_version != settings.catalog_schema_version:
        raise CatalogIdentityError("Unified DB schema version mismatch")
    expected_id = settings.new_catalog_instance_id
    if expected_id:
        try:
            if UUID(identity.id) != UUID(expected_id):
                raise CatalogIdentityError("Unified DB instance identity mismatch")
        except ValueError as exc:
            raise CatalogIdentityError("Invalid configured unified DB instance identity") from exc
    return identity.id


def get_catalog_session():
    url = catalog_url()
    if not url:
        raise HTTPException(503, "신규 통합 DB 연결이 설정되지 않았습니다.")
    try:
        with Session(catalog_engine(url), autoflush=False) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout='20s'"))
            verify_catalog_identity(session)
            try:
                yield session
            finally:
                session.rollback()
    except (SQLAlchemyError, CatalogIdentityError):
        raise HTTPException(503, "신규 통합 DB의 연결 또는 schema identity를 확인하세요.") from None
