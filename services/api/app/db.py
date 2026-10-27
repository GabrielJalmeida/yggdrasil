"""SQLAlchemy engine/session setup. Schema changes are managed by Alembic."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for persisted domain entities."""


def _make_engine() -> Engine:
    url = settings.database_url
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite:"):
        connect_args["check_same_thread"] = False
        if url.startswith("sqlite:///./"):
            Path("data").mkdir(parents=True, exist_ok=True)
    created_engine = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if url.startswith("sqlite:"):
        @event.listens_for(created_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return created_engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
