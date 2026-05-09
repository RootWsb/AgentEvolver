"""Asynchronously record sessions to SQLite without blocking responses."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from agent_evolver.storage.db import StorageSessionLocal
from agent_evolver.storage.models import Session, Message, ToolCall

logger = logging.getLogger("agent_evolver.recorder")


class SessionRecorder:
    """Fire-and-forget session recorder.

    Recording is fully asynchronous: the proxy responds to the agent
    immediately, and we write to SQLite in a background task.
    """

    MAX_PENDING = 100  # Flush oldest sessions when limit reached
    SESSION_TTL_SECONDS = 3600  # Auto-flush sessions older than 1 hour

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def start_session(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        task_desc: str | None = None,
    ) -> str:
        sid = session_id or str(uuid.uuid4())

        async with self._lock:
            # Evict stale sessions to prevent unbounded memory growth
            await self._evict_stale_and_overflow()

            # Only create if not already tracking this session
            if sid not in self._pending:
                self._pending[sid] = {
                    "agent_id": agent_id,
                    "user_id": user_id,
                    "task_desc": task_desc,
                    "messages": [],
                    "tool_calls": [],
                    "started_at": datetime.now(timezone.utc),
                }
        return sid

    @staticmethod
    def _consume_task_exception(task: asyncio.Task) -> None:
        """Consume any exception from a background task to prevent 'never retrieved' warnings."""
        try:
            task.result()
        except Exception:
            logger.exception("Background persist task failed")

    async def _evict_stale_and_overflow(self) -> None:
        """Remove stale or excess sessions. Must be called while holding self._lock."""
        now = datetime.now(timezone.utc)
        stale_sids: list[str] = []

        for sid, sess in self._pending.items():
            age = (now - sess["started_at"]).total_seconds()
            if age > self.SESSION_TTL_SECONDS:
                stale_sids.append(sid)

        # Flush stale sessions
        for sid in stale_sids:
            sess = self._pending.pop(sid, None)
            if sess:
                task = asyncio.create_task(
                    asyncio.to_thread(self._persist, sid, sess, None, "abandoned")
                )
                task.add_done_callback(self._consume_task_exception)

        # If still over limit, flush oldest
        while len(self._pending) >= self.MAX_PENDING:
            oldest_sid = min(
                self._pending, key=lambda s: self._pending[s]["started_at"]
            )
            oldest_sess = self._pending.pop(oldest_sid)
            task = asyncio.create_task(
                asyncio.to_thread(
                    self._persist, oldest_sid, oldest_sess, None, "abandoned"
                )
            )
            task.add_done_callback(self._consume_task_exception)

    async def record_message(
        self,
        session_id: str,
        role: str,
        content: str | None,
        tokens: int | None = None,
    ) -> None:
        async with self._lock:
            sess = self._pending.get(session_id)
            if sess:
                sess["messages"].append({
                    "role": role,
                    "content": content,
                    "tokens": tokens,
                    "ts": datetime.now(timezone.utc),
                })

    async def record_tool_call(
        self,
        session_id: str,
        tool_name: str,
        args: dict[str, Any] | None,
        result: str | None,
        status: str = "unknown",
    ) -> None:
        async with self._lock:
            sess = self._pending.get(session_id)
            if sess:
                sess["tool_calls"].append({
                    "tool_name": tool_name,
                    "args": args,
                    "result": result,
                    "status": status,
                    "ts": datetime.now(timezone.utc),
                })

    async def close_session(
        self,
        session_id: str,
        total_tokens: int | None = None,
        status: str = "completed",
    ) -> None:
        async with self._lock:
            sess = self._pending.pop(session_id, None)
        if not sess:
            return

        # Persist to SQLite (blocking IO → run in thread)
        await asyncio.to_thread(self._persist, session_id, sess, total_tokens, status)

    def _persist(
        self,
        session_id: str,
        sess: dict[str, Any],
        total_tokens: int | None,
        status: str,
    ) -> None:
        db = StorageSessionLocal()
        try:
            session = Session(
                id=session_id,
                agent_id=sess.get("agent_id"),
                user_id=sess.get("user_id"),
                task_desc=sess.get("task_desc"),
                status=status,
                total_tokens=total_tokens,
                started_at=sess["started_at"],
                ended_at=datetime.now(timezone.utc),
            )
            db.add(session)

            for m in sess.get("messages", []):
                db.add(Message(
                    session_id=session_id,
                    role=m["role"],
                    content=m.get("content"),
                    tokens=m.get("tokens"),
                    ts=m["ts"],
                ))

            for t in sess.get("tool_calls", []):
                db.add(ToolCall(
                    session_id=session_id,
                    tool_name=t["tool_name"],
                    args=t.get("args"),
                    result=t.get("result"),
                    status=t.get("status", "unknown"),
                    ts=t["ts"],
                ))

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


# Singleton recorder
_recorder: SessionRecorder | None = None


def get_recorder() -> SessionRecorder:
    global _recorder
    if _recorder is None:
        _recorder = SessionRecorder()
    return _recorder
