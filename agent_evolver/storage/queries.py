"""Query API for the evolution engine and dashboard."""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import func, desc
from sqlalchemy.orm import Session as DBSession

from agent_evolver.storage.models import Session, Message, ToolCall


def get_session_conversation(db: DBSession, session_id: str) -> list[dict[str, Any]]:
    """Return full conversation for a session as a list of dicts."""
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.ts)
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "ts": m.ts.isoformat(),
        }
        for m in messages
    ]


def get_session_tools(db: DBSession, session_id: str) -> list[dict[str, Any]]:
    """Return all tool calls for a session."""
    tcs = (
        db.query(ToolCall)
        .filter(ToolCall.session_id == session_id)
        .order_by(ToolCall.ts)
        .all()
    )
    return [
        {
            "tool_name": tc.tool_name,
            "args": tc.args,
            "result": tc.result,
            "status": tc.status,
            "ts": tc.ts.isoformat(),
        }
        for tc in tcs
    ]


def get_failed_tools(
    db: DBSession,
    since_hours: int = 24,
    min_failures: int = 3,
) -> list[tuple[str, int]]:
    """Return tools with >= min_failures errors in the last N hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    rows = (
        db.query(ToolCall.tool_name, func.count(ToolCall.id))
        .filter(ToolCall.status == "error", ToolCall.ts >= since)
        .group_by(ToolCall.tool_name)
        .having(func.count(ToolCall.id) >= min_failures)
        .all()
    )
    return [(row[0], row[1]) for row in rows]


def get_sessions_for_skill(
    db: DBSession,
    skill_name: str,
    limit: int = 50,
) -> list[Session]:
    """Get sessions where a skill was mentioned/invoked.

    This is a best-effort text search on message content.
    """
    # Escape SQL LIKE wildcards so skill_name is treated as literal text
    escaped = skill_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return (
        db.query(Session)
        .join(Message)
        .filter(Message.content.like(pattern, escape="\\"))
        .order_by(desc(Session.started_at))
        .limit(limit)
        .all()
    )


def get_tool_success_rate(
    db: DBSession,
    tool_name: str,
    window_hours: int = 24,
) -> float:
    """Return success rate (0.0-1.0) for a tool in the given window."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    total = (
        db.query(func.count(ToolCall.id))
        .filter(ToolCall.tool_name == tool_name, ToolCall.ts >= since)
        .scalar()
    )
    if not total:
        return 1.0  # No data = assume OK
    successes = (
        db.query(func.count(ToolCall.id))
        .filter(
            ToolCall.tool_name == tool_name,
            ToolCall.status == "success",
            ToolCall.ts >= since,
        )
        .scalar()
    )
    return successes / total


def get_metric_summary(db: DBSession, hours: int = 24) -> dict[str, Any]:
    """Dashboard metric summary."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    total_sessions = (
        db.query(func.count(Session.id))
        .filter(Session.started_at >= since)
        .scalar()
    )
    completed_sessions = (
        db.query(func.count(Session.id))
        .filter(Session.status == "completed", Session.started_at >= since)
        .scalar()
    )
    failed_sessions = (
        db.query(func.count(Session.id))
        .filter(Session.status == "failed", Session.started_at >= since)
        .scalar()
    )
    total_tokens = (
        db.query(func.sum(Session.total_tokens))
        .filter(Session.started_at >= since)
        .scalar()
    ) or 0

    return {
        "period_hours": hours,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "failed_sessions": failed_sessions,
        "total_tokens": total_tokens,
    }
