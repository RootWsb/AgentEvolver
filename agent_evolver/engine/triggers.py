"""Execution triggers — hooks that run after sessions complete.

MVP: only post-execution trigger (task_post).
Future: tool_degradation, metric_threshold triggers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_evolver.config import get_config
from agent_evolver.engine.evolver import run_evolution

logger = logging.getLogger("agent_evolver.triggers")

_config = get_config()


async def on_session_complete(
    db: Any,
    session_id: str,
    task_completed: bool = False,
    execution_note: str = "",
) -> list[dict[str, Any]]:
    """Trigger evolution analysis after a session completes.

    This is a fire-and-forget background task. It runs evolution
    asynchronously and does not block the response to the agent.
    """
    logger.info(
        "Trigger post-execution analysis: session=%s completed=%s",
        session_id,
        task_completed,
    )

    try:
        # Run evolution in threadpool to not block event loop
        results = await asyncio.to_thread(
            _run_evolution_sync,
            db,
            session_id,
            task_completed,
            execution_note,
        )

        if results:
            logger.info(
                "Evolution produced %d candidate(s) for session=%s",
                len(results),
                session_id,
            )
            for r in results:
                if r.get("success"):
                    logger.info(
                        "  - %s (v%d): %s",
                        r.get("candidate_id"),
                        r.get("version", 0),
                        r.get("skill_dir"),
                    )
                else:
                    logger.warning(
                        "  - failed: %s",
                        r.get("error"),
                    )
        else:
            logger.info("No evolution candidates produced for session=%s", session_id)

        return results

    except Exception as exc:
        logger.exception("Evolution trigger failed for session=%s: %s", session_id, exc)
        return []


def _run_evolution_sync(
    db: Any,
    session_id: str,
    task_completed: bool,
    execution_note: str,
) -> list[dict[str, Any]]:
    """Synchronous wrapper for run_evolution."""
    return run_evolution(
        db=db,
        session_id=session_id,
        task_completed=task_completed,
        execution_note=execution_note,
    )


def schedule_post_execution(
    db: Any,
    session_id: str,
    task_completed: bool = False,
    execution_note: str = "",
) -> asyncio.Task[list[dict[str, Any]]]:
    """Schedule post-execution analysis as a background task.

    Usage in FastAPI:
        @app.post("/v1/chat/completions")
        async def chat(request):
            ...
            if request.session_done:
                triggers.schedule_post_execution(db, session_id, task_completed=True)
            return response
    """
    return asyncio.create_task(
        on_session_complete(db, session_id, task_completed, execution_note)
    )
