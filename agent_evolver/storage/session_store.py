"""CRUD operations for sessions, messages, and tool calls."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session as DBSession

from agent_evolver.storage.models import Session, Message, ToolCall


def create_session(
    db: DBSession,
    session_id: str,
    agent_id: str | None = None,
    user_id: str | None = None,
    task_desc: str | None = None,
) -> Session:
    session = Session(
        id=session_id,
        agent_id=agent_id,
        user_id=user_id,
        task_desc=task_desc,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: DBSession, session_id: str) -> Session | None:
    return db.query(Session).filter(Session.id == session_id).first()


def list_sessions(
    db: DBSession,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> list[Session]:
    q = db.query(Session)
    if status:
        q = q.filter(Session.status == status)
    return q.order_by(desc(Session.started_at)).offset(offset).limit(limit).all()


def update_session_status(
    db: DBSession,
    session_id: str,
    status: str,
    total_tokens: int | None = None,
) -> Session | None:
    session = get_session(db, session_id)
    if not session:
        return None
    session.status = status
    if total_tokens is not None:
        session.total_tokens = total_tokens
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


def add_message(
    db: DBSession,
    session_id: str,
    role: str,
    content: str | None,
    tokens: int | None = None,
) -> Message:
    msg = Message(
        session_id=session_id,
        role=role,
        content=content,
        tokens=tokens,
        ts=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_messages(db: DBSession, session_id: str) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.ts)
        .all()
    )


def add_tool_call(
    db: DBSession,
    session_id: str,
    tool_name: str,
    args: dict[str, Any] | None,
    result: str | None,
    status: str = "unknown",
) -> ToolCall:
    tc = ToolCall(
        session_id=session_id,
        tool_name=tool_name,
        args=args,
        result=result,
        status=status,
        ts=datetime.now(timezone.utc),
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return tc


def get_tool_calls(db: DBSession, session_id: str) -> list[ToolCall]:
    return (
        db.query(ToolCall)
        .filter(ToolCall.session_id == session_id)
        .order_by(ToolCall.ts)
        .all()
    )


def get_recent_sessions(
    db: DBSession,
    hours: int = 24,
    limit: int = 100,
) -> list[Session]:
    """Get sessions from the last N hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return (
        db.query(Session)
        .filter(Session.started_at >= since)
        .order_by(desc(Session.started_at))
        .limit(limit)
        .all()
    )
