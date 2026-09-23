from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def get_engine() -> Engine:
    raise RuntimeError("Legacy SQL access is disabled; use catalog_session")


def _engine_for_url(url: str) -> Engine:
    raise RuntimeError("Legacy SQL access is disabled; use catalog_session")


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for a transaction-scoped SQLAlchemy session."""
    factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
