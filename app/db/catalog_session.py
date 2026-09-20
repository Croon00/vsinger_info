"""Read-only pool for the new catalog; never falls back to the legacy DATABASE_URL."""
from functools import lru_cache
from pathlib import Path
import os
from dotenv import dotenv_values
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

def catalog_url():
    configured = os.environ.get("NEW_CATALOG_DATABASE_URL", "")
    if not configured:
        configured = dotenv_values(Path(__file__).resolve().parents[2] / ".env.catalog").get("NEW_CATALOG_DATABASE_URL", "")
    return configured or ""

@lru_cache(maxsize=4)
def catalog_engine(url):
    return create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1).replace("postgres://", "postgresql+psycopg://", 1),
                         pool_pre_ping=True, pool_size=5, max_overflow=5, pool_timeout=15, pool_recycle=300,
                         connect_args={"connect_timeout": 10}, hide_parameters=True)

def get_catalog_session():
    url = catalog_url()
    if not url:
        raise HTTPException(503, "새 카탈로그 DB 연결이 설정되지 않았습니다.")
    try:
        with Session(catalog_engine(url), autoflush=False) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout='20s'"))
            try:
                yield session
            finally:
                session.rollback()
    except SQLAlchemyError:
        raise HTTPException(503, "새 카탈로그를 조회할 수 없습니다. 연결 상태를 확인하세요.") from None
