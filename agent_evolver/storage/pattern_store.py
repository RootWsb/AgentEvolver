"""Store and query discovered patterns for statistical validation.

Every time the analyzer detects a pattern, it is recorded via
record_pattern_occurrence(). Over time, this builds evidence for
whether a pattern is a statistical fluke or a genuine recurring pattern
worthy of CAPTURED evolution.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from agent_evolver.storage.db import StorageSessionLocal
from agent_evolver.storage.models import PatternOccurrence

logger = logging.getLogger("agent_evolver.pattern_store")


def _get_db_session() -> DBSession:
    """Get a storage DB session for direct use."""
    return StorageSessionLocal()


def compute_pattern_hash(pattern_type: str, pattern_data: dict[str, Any]) -> str:
    """Compute a stable hash for a pattern for deduplication.

    Uses SHA256 of a canonical JSON representation. Returns first 32 chars
    for index-friendly fixed-length keys.
    """
    # Sort keys for canonicalization
    canonical = json.dumps({"type": pattern_type, "data": pattern_data}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def record_pattern_occurrence(
    pattern_type: str,
    pattern_data: dict[str, Any],
    session_id: str,
    similarity_score: float,
    db: DBSession | None = None,
) -> str:
    """Record that a pattern was observed in a session.

    Returns the pattern_hash for correlation with other occurrences.
    """
    pattern_hash = compute_pattern_hash(pattern_type, pattern_data)

    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        occurrence = PatternOccurrence(
            pattern_hash=pattern_hash,
            pattern_type=pattern_type,
            session_id=session_id,
            similarity_score=similarity_score,
        )
        db.add(occurrence)
        db.commit()
        logger.debug(
            "Recorded pattern occurrence: hash=%s type=%s session=%s",
            pattern_hash, pattern_type, session_id,
        )
        return pattern_hash
    except Exception:
        db.rollback()
        logger.exception("Failed to record pattern occurrence")
        raise
    finally:
        if should_close:
            db.close()


def get_pattern_stats(
    pattern_hash: str,
    min_similarity: float = 0.7,
    db: DBSession | None = None,
) -> dict[str, Any]:
    """Get occurrence statistics for a pattern.

    Returns:
        {
            "total_occurrences": int,
            "unique_sessions": int,
            "avg_similarity": float,
            "captured_as_skill": str | None,
        }
    """
    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        # Aggregate stats
        stmt = (
            select(
                func.count().label("total"),
                func.count(PatternOccurrence.session_id.distinct()).label(
                    "unique_sessions"
                ),
                func.avg(PatternOccurrence.similarity_score).label("avg_similarity"),
            )
            .where(PatternOccurrence.pattern_hash == pattern_hash)
            .where(PatternOccurrence.similarity_score >= min_similarity)
        )
        result = db.execute(stmt).one()

        # Check if already captured as a skill
        captured = db.execute(
            select(PatternOccurrence.captured_as_skill)
            .where(PatternOccurrence.pattern_hash == pattern_hash)
            .where(PatternOccurrence.captured_as_skill.isnot(None))
            .limit(1)
        ).scalar()

        return {
            "total_occurrences": result.total or 0,
            "unique_sessions": result.unique_sessions or 0,
            "avg_similarity": float(result.avg_similarity or 0),
            "captured_as_skill": captured,
        }
    finally:
        if should_close:
            db.close()


def mark_pattern_captured(
    pattern_hash: str,
    candidate_id: str,
    db: DBSession | None = None,
) -> int:
    """Mark all occurrences of a pattern as captured by a skill candidate.

    Returns the number of rows updated.
    """
    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        result = (
            db.query(PatternOccurrence)
            .filter(PatternOccurrence.pattern_hash == pattern_hash)
            .update({"captured_as_skill": candidate_id})
        )
        db.commit()
        logger.info(
            "Marked pattern %s as captured by %s (%d rows)",
            pattern_hash, candidate_id, result,
        )
        return result
    except Exception:
        db.rollback()
        logger.exception("Failed to mark pattern as captured")
        raise
    finally:
        if should_close:
            db.close()


def find_patterns_for_session(
    session_id: str,
    db: DBSession | None = None,
) -> list[dict[str, Any]]:
    """Find all patterns recorded for a specific session."""
    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        rows = (
            db.query(PatternOccurrence)
            .filter(PatternOccurrence.session_id == session_id)
            .all()
        )
        return [
            {
                "pattern_hash": r.pattern_hash,
                "pattern_type": r.pattern_type,
                "similarity_score": r.similarity_score,
                "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
                "captured_as_skill": r.captured_as_skill,
            }
            for r in rows
        ]
    finally:
        if should_close:
            db.close()
