"""Post-execution session analyzer.

Analyzes a completed session and produces evolution suggestions.
Simplified from OpenSpace analyzer — no external dependencies beyond storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as DBSession

from agent_evolver.engine.types import (
    EvolutionSuggestion,
    EvolutionType,
    ExecutionAnalysis,
    SkillJudgment,
    SkillCategory,
)
from agent_evolver.config import get_config
from agent_evolver.storage.queries import (
    get_session_conversation,
    get_session_tools,
    get_failed_tools,
)
from agent_evolver.storage.semantic_queries import (
    find_similar_sessions,
    find_recurring_tool_sequences,
)
from agent_evolver.storage.session_store import get_session

_config = get_config()


def analyze_session(
    db: DBSession,
    session_id: str,
    task_completed: bool = False,
    execution_note: str = "",
) -> ExecutionAnalysis:
    """Analyze a completed session and return judgments + suggestions.

    Enhanced with cross-session semantic pattern mining:
    1. Find historically similar sessions
    2. Detect recurring patterns across similar sessions
    3. Boost CAPTURED confidence based on statistical evidence
    """
    # Gather data
    conversation = get_session_conversation(db, session_id)
    tools = get_session_tools(db, session_id)

    # Identify failed tools
    failed_tool_names = {t["tool_name"] for t in tools if t["status"] == "error"}
    tool_issues = list(failed_tool_names)

    # Build skill judgments (best-effort text matching)
    skill_judgments = _infer_skill_judgments(conversation, tools)

    # ── Cross-session semantic pattern mining ──
    cross_session_evidence: dict[str, Any] = {}
    cross_session_patterns: list[dict[str, Any]] = []
    pattern_confidence_boost = 0.0

    # Get session task description for semantic lookup
    session = get_session(db, session_id)
    task_desc = session.task_desc if session else None

    if task_desc:
        similar_sessions = find_similar_sessions(
            task_description=task_desc,
            min_similarity=_config.evolver_semantic_min_similarity,
            limit=_config.evolver_semantic_max_sessions,
            db=db,
        )

        if len(similar_sessions) >= _config.evolver_pattern_min_occurrences:
            # Extract session IDs from similar sessions
            similar_session_ids = [s["id"] for s in similar_sessions if s["id"] != session_id]

            if similar_session_ids:
                # Look for recurring tool sequences
                recurring = find_recurring_tool_sequences(
                    session_ids=similar_session_ids,
                    min_occurrences=_config.evolver_pattern_min_occurrences,
                    db=db,
                )

                if recurring:
                    cross_session_patterns = recurring
                    # More recurring patterns = higher confidence boost
                    pattern_confidence_boost = min(
                        _config.evolver_pattern_confidence_boost_max,
                        len(recurring) * 0.05,
                    )

        cross_session_evidence = {
            "similar_session_count": len(similar_sessions),
            "recurring_patterns": cross_session_patterns,
            "confidence_boost": pattern_confidence_boost,
        }

    # Generate evolution suggestions
    evolution_suggestions: list[EvolutionSuggestion] = []

    # Suggestion 1: FIX for tools that repeatedly fail
    if failed_tool_names:
        # Query once for all failed tools in the window
        recent_fails = get_failed_tools(db, since_hours=24, min_failures=1)
        fail_counts = {t: c for t, c in recent_fails}

        for tool_name in failed_tool_names:
            fail_count = fail_counts.get(tool_name, 0)
            if fail_count >= 3:
                confidence = min(0.5 + (fail_count - 3) * 0.1, 0.95)
                evolution_suggestions.append(
                    EvolutionSuggestion(
                        evolution_type=EvolutionType.FIX,
                        target_skill_ids=[_tool_to_skill_name(tool_name)],
                        category=SkillCategory.TOOL_GUIDE,
                        direction="fix",
                        confidence=confidence,
                        reason=f"Tool '{tool_name}' failed {fail_count} times in 24h. "
                        f"Suggested fix: review error patterns and update handling.",
                    )
                )

    # Suggestion 2: CAPTURED for successful patterns with no matching skill
    if task_completed and not any(j.skill_applied for j in skill_judgments):
        # Task completed without any skill being explicitly applied
        # This is a candidate for capturing a new workflow
        base_confidence = 0.6
        boosted_confidence = min(1.0, base_confidence + pattern_confidence_boost)

        reason = (
            "Task completed successfully without skill assistance. "
            "Conversation pattern may be capturable as a reusable workflow."
        )
        if cross_session_patterns:
            reason += (
                f"\n\n[Cross-session validation: {len(similar_sessions)} similar "
                f"sessions found, {len(cross_session_patterns)} recurring patterns detected.]"
            )

        evolution_suggestions.append(
            EvolutionSuggestion(
                evolution_type=EvolutionType.CAPTURED,
                target_skill_ids=[],
                category=SkillCategory.WORKFLOW,
                direction="capture",
                confidence=boosted_confidence,
                reason=reason,
            )
        )

    return ExecutionAnalysis(
        task_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_completed=task_completed,
        execution_note=execution_note,
        tool_issues=tool_issues,
        skill_judgments=skill_judgments,
        evolution_suggestions=evolution_suggestions,
        cross_session_evidence=cross_session_evidence,
        analyzed_by="agent-evolver",
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


def _infer_skill_judgments(
    conversation: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> list[SkillJudgment]:
    """Infer which skills were applied based on conversation content.

    MVP: simple keyword matching. Future: semantic embedding match.
    """
    judgments: list[SkillJudgment] = []
    seen_skills: set[str] = set()

    # Look for skill mentions in assistant messages
    for msg in conversation:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content") or ""
        # Simple heuristic: look for "Using skill:" or similar patterns
        if "skill" in content.lower():
            # Extract potential skill names (naive)
            for line in content.split("\n"):
                if "skill" in line.lower() and ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        remainder = parts[1].strip()
                        if remainder:
                            skill_name = remainder.split()[0]
                            if skill_name and skill_name not in seen_skills:
                                seen_skills.add(skill_name)
                                judgments.append(
                                    SkillJudgment(
                                        skill_id=skill_name,
                                        skill_applied=True,
                                        note="Detected from conversation text",
                                    )
                                )

    # If no skills detected but tools were used successfully, note that
    if not judgments:
        successful_tools = [t["tool_name"] for t in tools if t["status"] == "success"]
        if successful_tools:
            for tool_name in set(successful_tools):
                judgments.append(
                    SkillJudgment(
                        skill_id=_tool_to_skill_name(tool_name),
                        skill_applied=True,
                        note="Inferred from successful tool call",
                    )
                )

    return judgments


def _tool_to_skill_name(tool_name: str) -> str:
    """Map a tool name to a canonical skill name."""
    # Simple normalization
    return tool_name.replace("_", "-").lower()


def store_analysis(db: DBSession, analysis: ExecutionAnalysis) -> None:
    """Store analysis result as a JSON message in the session record."""
    # For MVP, we store the analysis as a system message in the conversation
    from agent_evolver.storage.session_store import add_message

    content = (
        f"[EVOLUTION_ANALYSIS] task_completed={analysis.task_completed} "
        f"tool_issues={analysis.tool_issues} "
        f"suggestions={len(analysis.evolution_suggestions)}"
    )
    add_message(
        db=db,
        session_id=analysis.task_id,
        role="system",
        content=content,
    )
