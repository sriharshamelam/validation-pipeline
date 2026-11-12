"""SQLAlchemy engine factory and session management."""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def get_engine(db_url: str | None = None):
    """Return (and cache) the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        url = db_url or settings.get_db_url()
        _engine = create_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


def get_session_factory(db_url: str | None = None):
    """Return (and cache) the session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine(db_url)
        _SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _SessionFactory


@contextmanager
def get_session(db_url: str | None = None) -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    factory = get_session_factory(db_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection(db_url: str | None = None) -> bool:
    """Ping MySQL and return True if the connection succeeds."""
    try:
        engine = get_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError as exc:
        logger.warning("MySQL connection test failed: %s", exc)
        return False


def reset_engine() -> None:
    """Dispose the cached engine (used in tests)."""
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
