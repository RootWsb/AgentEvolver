"""SQLite database engine and session factory."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from agent_evolver.config import get_config

Base = declarative_base()

# Lazily-initialized engine so tests can reset config between runs.
_storage_engine = None
_db_initialized = False


def _get_storage_engine():
    """Return (or create) the storage SQLite engine."""
    global _storage_engine
    if _storage_engine is None:
        config = get_config()
        _storage_engine = create_engine(
            f"sqlite:///{config.storage_db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )

        @event.listens_for(_storage_engine, "connect")
        def _enable_wal(dbapi_conn, connection_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return _storage_engine


def _get_storage_session_local():
    """Return a session bound to the current engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=_get_storage_engine())


class _LazySessionMaker:
    """Lazy sessionmaker that rebinds when the engine changes."""

    def __call__(self):
        return _get_storage_session_local()()


StorageSessionLocal = _LazySessionMaker()


def _ensure_storage_db():
    """Create tables if they haven't been created yet."""
    global _db_initialized
    if not _db_initialized:
        Base.metadata.create_all(bind=_get_storage_engine())
        _db_initialized = True


def init_storage_db():
    """Explicit table creation (called at app startup)."""
    _ensure_storage_db()


def reset_storage_engine():
    """Drop and recreate the engine (used only in tests)."""
    global _storage_engine, _db_initialized
    _storage_engine = None
    _db_initialized = False


def get_storage_session():
    session = StorageSessionLocal()
    try:
        yield session
    finally:
        session.close()
