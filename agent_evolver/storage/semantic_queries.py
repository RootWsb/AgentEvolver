"""Semantic query layer using FTS5 for pattern discovery.

Provides cross-session pattern mining capabilities:
1. Find historically similar completed sessions
2. Detect recurring tool call sequences
3. Identify repeating message patterns

MVP: Falls back to LIKE-based search if FTS5 is not available.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from agent_evolver.storage.db import StorageSessionLocal
from agent_evolver.storage.models import Session, Message, ToolCall

logger = logging.getLogger("agent_evolver.semantic_queries")


def _get_db_session() -> DBSession:
    """Get a storage DB session for direct use (non-generator)."""
    return StorageSessionLocal()


def _check_fts5_available(db: DBSession) -> bool:
    """Check if FTS5 virtual table exists for messages."""
    try:
        result = db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'")
        ).scalar()
        return result is not None
    except Exception:
        return False


def _build_fts5_pattern(task_description: str) -> str:
    """Convert task description to FTS5 query pattern.

    e.g., "deploy docker container" -> "deploy* docker* container*"
    """
    words = task_description.strip().split()
    return " ".join(f"{word}*" for word in words if len(word) >= 2)


def find_similar_sessions(
    task_description: str,
    min_similarity: float = 0.7,
    limit: int = 20,
    db: DBSession | None = None,
) -> list[dict[str, Any]]:
    """Find historically similar completed sessions.

    Uses FTS5 when available, falls back to LIKE-based search otherwise.
    Only returns sessions with status='completed' to learn from successes.
    """
    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        fts5_available = _check_fts5_available(db)
        pattern = _build_fts5_pattern(task_description)

        if fts5_available and pattern:
            return _find_similar_sessions_fts5(db, pattern, limit)
        else:
            return _find_similar_sessions_like(db, task_description, limit)
    finally:
        if should_close:
            db.close()


def _find_similar_sessions_fts5(
    db: DBSession,
    pattern: str,
    limit: int,
) -> list[dict[str, Any]]:
    """FTS5-powered similar session search."""
    query = text("""
        SELECT
            s.id,
            s.task_desc,
            s.status,
            s.started_at,
            rank
        FROM sessions s
        JOIN messages_fts fts ON s.id = fts.session_id
        WHERE messages_fts MATCH :pattern
          AND s.status = 'completed'
        ORDER BY rank
        LIMIT :limit
    """)

    try:
        rows = db.execute(query, {"pattern": pattern, "limit": limit}).mappings().all()
        return [
            {
                "id": row["id"],
                "task_desc": row["task_desc"],
                "status": row["status"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "rank": row["rank"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning("FTS5 query failed, falling back: %s", e)
        return []


def _find_similar_sessions_like(
    db: DBSession,
    task_description: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fallback LIKE-based similar session search.

    Splits task description into keywords and searches for sessions
    whose task_desc or messages contain any of the keywords.
    """
    # Extract meaningful keywords (length >= 3)
    keywords = [w.lower() for w in task_description.split() if len(w) >= 3]
    if not keywords:
        return []

    # Build OR condition for task_desc LIKE
    like_conditions = []
    for kw in keywords:
        like_conditions.append(f"s.task_desc LIKE '%{kw}%'")

    # Also check message content
    msg_conditions = []
    for kw in keywords:
        msg_conditions.append(f"m.content LIKE '%{kw}%'")

    where_clause = " OR ".join(like_conditions + msg_conditions)

    query = text(f"""
        SELECT DISTINCT
            s.id,
            s.task_desc,
            s.status,
            s.started_at
        FROM sessions s
        LEFT JOIN messages m ON s.id = m.session_id
        WHERE ({where_clause})
          AND s.status = 'completed'
        ORDER BY s.started_at DESC
        LIMIT :limit
    """)

    try:
        rows = db.execute(query, {"limit": limit}).mappings().all()
        return [
            {
                "id": row["id"],
                "task_desc": row["task_desc"],
                "status": row["status"],
                "started_at": (
                    row["started_at"].isoformat()
                    if hasattr(row["started_at"], "isoformat")
                    else row["started_at"]
                ),
                "rank": 0,  # no ranking in LIKE fallback
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning("LIKE fallback query failed: %s", e)
        return []


def find_recurring_tool_sequences(
    session_ids: list[str],
    min_occurrences: int = 3,
    db: DBSession | None = None,
) -> list[dict[str, Any]]:
    """Find tool call sequences that appear across multiple sessions.

    A 'sequence' is an ordered list of tool names (without arguments)
    that appear in the same order within a session.
    """
    if len(session_ids) < min_occurrences:
        return []

    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        # Fetch tool calls for the given sessions, ordered by time
        tool_calls = (
            db.query(ToolCall)
            .filter(ToolCall.session_id.in_(session_ids))
            .filter(ToolCall.status == "success")
            .order_by(ToolCall.session_id, ToolCall.ts)
            .all()
        )

        # Group by session and build sequences
        from collections import defaultdict
        session_sequences: dict[str, list[str]] = defaultdict(list)
        for tc in tool_calls:
            session_sequences[tc.session_id].append(tc.tool_name)

        # Convert to string sequences and count occurrences
        sequence_counts: dict[str, dict[str, Any]] = {}
        for sid, tools in session_sequences.items():
            if len(tools) < 2:
                continue
            seq_str = "->".join(tools)
            if seq_str not in sequence_counts:
                sequence_counts[seq_str] = {
                    "sequence": tools,
                    "occurrence_count": 0,
                    "sessions": set(),
                }
            sequence_counts[seq_str]["occurrence_count"] += 1
            sequence_counts[seq_str]["sessions"].add(sid)

        # Filter by minimum occurrences across unique sessions
        results = []
        for seq_str, data in sequence_counts.items():
            unique_sessions = len(data["sessions"])
            if unique_sessions >= min_occurrences:
                results.append({
                    "sequence": data["sequence"],
                    "sequence_str": seq_str,
                    "occurrence_count": data["occurrence_count"],
                    "unique_sessions": unique_sessions,
                    "sessions": list(data["sessions"]),
                })

        # Sort by occurrence count descending
        results.sort(key=lambda x: x["occurrence_count"], reverse=True)
        return results

    finally:
        if should_close:
            db.close()


def find_message_patterns(
    session_ids: list[str],
    role: str = "assistant",
    min_occurrences: int = 3,
    db: DBSession | None = None,
) -> list[dict[str, Any]]:
    """Find recurring message content patterns using simple n-gram overlap.

    MVP: Uses common substring detection. Future: upgrade to embeddings.
    """
    if len(session_ids) < min_occurrences:
        return []

    should_close = False
    if db is None:
        db = _get_db_session()
        should_close = True

    try:
        messages = (
            db.query(Message)
            .filter(Message.session_id.in_(session_ids))
            .filter(Message.role == role)
            .filter(Message.content.isnot(None))
            .all()
        )

        if len(messages) < min_occurrences:
            return []

        # Extract common phrases (3-5 word n-grams)
        from collections import Counter

        ngram_counts: Counter = Counter()
        for msg in messages:
            content = msg.content or ""
            words = re.findall(r"\b[a-zA-Z]{3,}\b", content.lower())
            for n in range(3, 6):
                for i in range(len(words) - n + 1):
                    ngram = " ".join(words[i : i + n])
                    ngram_counts[ngram] += 1

        # Filter for n-grams that appear across multiple messages
        results = []
        for ngram, count in ngram_counts.most_common(20):
            if count >= min_occurrences:
                results.append({
                    "pattern": ngram,
                    "occurrence_count": count,
                    "pattern_type": "ngram",
                })

        return results

    finally:
        if should_close:
            db.close()
