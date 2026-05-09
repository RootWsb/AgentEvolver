"""Candidate skill store — SQLite-backed version tracking and status management."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    DateTime,
    create_engine,
    event,
)
from sqlalchemy.orm import sessionmaker, declarative_base

from agent_evolver.config import get_config
from agent_evolver.engine.types import CandidateStatus
from agent_evolver.security.path_guard import assert_candidate_path, get_candidate_skill_dir

Base = declarative_base()

# Lazily-initialized engine so tests can reset config between runs.
_candidate_engine = None
_db_initialized = False


def _get_engine():
    """Return (or create) the candidate SQLite engine."""
    global _candidate_engine
    if _candidate_engine is None:
        config = get_config()
        _candidate_engine = create_engine(
            f"sqlite:///{config.candidate_db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )

        @event.listens_for(_candidate_engine, "connect")
        def _enable_wal(dbapi_conn, connection_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return _candidate_engine


def _get_session_local():
    """Return a session bound to the current engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())


def _ensure_db():
    """Create tables if they haven't been created yet."""
    global _db_initialized
    if not _db_initialized:
        Base.metadata.create_all(bind=_get_engine())
        _db_initialized = True


def init_candidate_db():
    """Explicit table creation (called at app startup)."""
    _ensure_db()


def reset_candidate_engine():
    """Drop and recreate the engine (used only in tests)."""
    global _candidate_engine, _db_initialized
    _candidate_engine = None
    _db_initialized = False


def get_candidate_session():
    session = _get_session_local()()
    try:
        yield session
    finally:
        session.close()


class CandidateRecord(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String(512), unique=True, nullable=False, index=True)
    skill_name = Column(String(256), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=0)
    status = Column(
        String(32), default="pending"
    )  # pending | auto_validated | approved | rejected | published
    evolution_type = Column(String(32), nullable=False)
    confidence_score = Column(Float, nullable=False, default=0.0)
    mutation_json_path = Column(Text, nullable=True)
    skill_dir_path = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    published_at = Column(DateTime, nullable=True)
    approver_id = Column(String(128), nullable=True)


def _next_version(skill_name: str, db: Any) -> int:
    """Return the next version number for a skill."""
    from sqlalchemy import func

    max_ver = (
        db.query(func.max(CandidateRecord.version))
        .filter(CandidateRecord.skill_name == skill_name)
        .scalar()
    )
    return (max_ver or 0) + 1


def create_candidate(
    skill_name: str,
    evolution_type: str,
    confidence_score: float,
    reason: str = "",
    skill_files: dict[str, str] | None = None,
    mutation_dict: dict[str, Any] | None = None,
    version: int | None = None,
) -> tuple[str, Path]:
    """Create a new candidate skill version.

    Args:
        version: Optional explicit version number. If None, auto-increments.

    Returns (candidate_id, skill_dir_path).
    """
    import uuid

    _ensure_db()
    db = _get_session_local()()
    try:
        if version is None:
            version = _next_version(skill_name, db)
        candidate_id = f"{skill_name}~v{version}~{uuid.uuid4().hex[:8]}"

        config = get_config()
        skill_dir = get_candidate_skill_dir(skill_name, version)
        assert_candidate_path(skill_dir)
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write skill files (supports nested paths like "docs/README.md")
        if skill_files:
            for filename, content in skill_files.items():
                file_path = skill_dir / filename
                assert_candidate_path(file_path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

        # Write mutation.json
        mutation_path = skill_dir / "mutation.json"
        if mutation_dict:
            mutation_path.write_text(
                json.dumps(mutation_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        record = CandidateRecord(
            candidate_id=candidate_id,
            skill_name=skill_name,
            version=version,
            status=CandidateStatus.PENDING.value,
            evolution_type=evolution_type,
            confidence_score=confidence_score,
            mutation_json_path=str(mutation_path) if mutation_dict else None,
            skill_dir_path=str(skill_dir),
            reason=reason,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.commit()

        return candidate_id, skill_dir
    finally:
        db.close()


def get_candidate(candidate_id: str) -> CandidateRecord | None:
    _ensure_db()
    db = _get_session_local()()
    try:
        return (
            db.query(CandidateRecord)
            .filter(CandidateRecord.candidate_id == candidate_id)
            .first()
        )
    finally:
        db.close()


def list_candidates(
    skill_name: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CandidateRecord]:
    _ensure_db()
    db = _get_session_local()()
    try:
        q = db.query(CandidateRecord)
        if skill_name:
            q = q.filter(CandidateRecord.skill_name == skill_name)
        if status:
            q = q.filter(CandidateRecord.status == status)
        return (
            q.order_by(CandidateRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    finally:
        db.close()


def update_status(
    candidate_id: str,
    status: str,
    approver_id: str | None = None,
) -> CandidateRecord | None:
    _ensure_db()
    db = _get_session_local()()
    try:
        rec = (
            db.query(CandidateRecord)
            .filter(CandidateRecord.candidate_id == candidate_id)
            .first()
        )
        if not rec:
            return None
        rec.status = status
        rec.updated_at = datetime.now(timezone.utc)
        if status == CandidateStatus.PUBLISHED.value:
            rec.published_at = datetime.now(timezone.utc)
        if approver_id:
            rec.approver_id = approver_id
        db.commit()
        db.refresh(rec)
        return rec
    finally:
        db.close()


def archive_rejected(candidate_id: str) -> Path | None:
    """Move a rejected candidate to archive directory."""
    rec = get_candidate(candidate_id)
    if not rec or rec.status != CandidateStatus.REJECTED.value:
        return None

    config = get_config()
    skill_dir = Path(rec.skill_dir_path)
    archive_dir = (
        config.evolver_candidate_dir / "archive" / rec.skill_name / f"v{rec.version}"
    )
    assert_candidate_path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    if skill_dir.exists():
        for f in skill_dir.iterdir():
            shutil.move(str(f), str(archive_dir / f.name))
        # Remove the now-empty skill dir (ignore errors if non-empty)
        shutil.rmtree(skill_dir, ignore_errors=True)

    return archive_dir


def get_skill_versions(skill_name: str) -> list[CandidateRecord]:
    _ensure_db()
    db = _get_session_local()()
    try:
        return (
            db.query(CandidateRecord)
            .filter(CandidateRecord.skill_name == skill_name)
            .order_by(CandidateRecord.version.desc())
            .all()
        )
    finally:
        db.close()
