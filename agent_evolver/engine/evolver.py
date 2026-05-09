"""Evolution engine — applies FIX and CAPTURED evolutions.

Coordinates analyzer → patch pipeline. All disk writes go through patch.py
which enforces candidate-directory-only writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_evolver.config import get_config
from agent_evolver.engine.analyzer import analyze_session
from agent_evolver.engine.patch import fix_skill, create_skill
from agent_evolver.engine.types import (
    EvolutionSuggestion,
    EvolutionType,
    ExecutionAnalysis,
)
from agent_evolver.protocol.audit import log_evolution
from agent_evolver.protocol.sanitize import sanitize

_config = get_config()


def run_evolution(
    db: Any,
    session_id: str,
    task_completed: bool = False,
    execution_note: str = "",
    min_confidence: float | None = None,
) -> list[dict[str, Any]]:
    """Run full evolution pipeline on a completed session.

    1. Analyze session → get suggestions
    2. Filter by confidence threshold
    3. Apply evolution (FIX → patch fix_skill, CAPTURED → patch create_skill)
    4. Log audit events

    Returns list of evolution results.
    """
    if min_confidence is None:
        min_confidence = _config.evolver_confidence_threshold

    # Step 1: Analyze
    analysis = analyze_session(db, session_id, task_completed, execution_note)

    results: list[dict[str, Any]] = []

    # Step 2 + 3: Filter and apply
    for suggestion in analysis.evolution_suggestions:
        if suggestion.confidence < min_confidence:
            continue

        result = _apply_suggestion(suggestion, analysis)
        if result and result.get("success"):
            results.append(result)

    return results


def _apply_suggestion(
    suggestion: EvolutionSuggestion,
    analysis: ExecutionAnalysis,
) -> dict[str, Any] | None:
    """Apply a single evolution suggestion."""

    if suggestion.evolution_type == EvolutionType.FIX:
        if not suggestion.target_skill_ids:
            return None
        skill_name = suggestion.target_skill_ids[0]

        # Build fix instructions from analysis
        fix_instructions = _build_fix_instructions(skill_name, analysis)

        patch_result = fix_skill(
            skill_name=skill_name,
            fix_instructions=fix_instructions,
            confidence_score=suggestion.confidence,
            reason=sanitize(suggestion.reason),
        )

        if patch_result.get("success"):
            log_evolution(
                mutation_id=patch_result["candidate_id"],
                skill_name=skill_name,
                version=patch_result["version"],
                evolution_type=EvolutionType.FIX.value,
                confidence=suggestion.confidence,
                candidate_path=patch_result["skill_dir"],
            )

        return patch_result

    elif suggestion.evolution_type == EvolutionType.CAPTURED:
        # Generate a skill name from the analysis context
        skill_name = _generate_skill_name(analysis)

        # Build skill content from conversation patterns
        content = _build_captured_skill(analysis)

        patch_result = create_skill(
            skill_name=skill_name,
            content=content,
            confidence_score=suggestion.confidence,
            reason=sanitize(suggestion.reason),
        )

        if patch_result.get("success"):
            log_evolution(
                mutation_id=patch_result["candidate_id"],
                skill_name=skill_name,
                version=patch_result["version"],
                evolution_type=EvolutionType.CAPTURED.value,
                confidence=suggestion.confidence,
                candidate_path=patch_result["skill_dir"],
            )

        return patch_result

    elif suggestion.evolution_type == EvolutionType.DERIVED:
        # MVP: DERIVED is out of scope, skip
        return None

    return None


def _build_fix_instructions(skill_name: str, analysis: ExecutionAnalysis) -> str:
    """Build fix instructions from tool failures and execution notes."""
    lines = [
        f"# Fix for skill: {skill_name}",
        "",
        "## Issues detected:",
    ]
    for issue in analysis.tool_issues:
        lines.append(f"- Tool error: {issue}")
    if analysis.execution_note:
        lines.append(f"- Execution note: {analysis.execution_note}")
    lines.extend([
        "",
        "## Suggested fixes:",
        "1. Review error handling in the skill implementation.",
        "2. Add input validation if missing.",
        "3. Update tool call patterns to match current API.",
    ])
    return "\n".join(lines)


import re


def _generate_skill_name(analysis: ExecutionAnalysis) -> str:
    """Generate a skill name from the task context."""
    # Use task_id as base, sanitize for filesystem
    base = analysis.task_id.lower()
    # Replace any character that is not alphanumeric or underscore
    base = re.sub(r"[^a-z0-9_]", "_", base)
    # Collapse multiple underscores
    base = re.sub(r"_+", "_", base)
    # Strip leading/trailing underscores
    base = base.strip("_")
    # Truncate and add prefix
    base = base[:40] if len(base) > 40 else base
    return f"captured_{base}"


def _build_captured_skill(analysis: ExecutionAnalysis) -> dict[str, str]:
    """Build skill file content from a successful execution pattern."""
    skill_name = _generate_skill_name(analysis)

    return {
        "SKILL.md": (
            f"# {skill_name}\n\n"
            f"## Description\n\n"
            f"Auto-captured workflow from successful task execution.\n\n"
            f"## When to Use\n\n"
            f"- Task completed successfully without skill assistance\n"
            f"- Pattern recognized from session {analysis.task_id}\n\n"
            f"## Steps\n\n"
            f"_This skill was automatically generated. Human review recommended._\n\n"
            f"## Source\n\n"
            f"- Task ID: {analysis.task_id}\n"
            f"- Captured at: {analysis.timestamp}\n"
        ),
        "README.md": (
            f"# {skill_name}\n\n"
            f"Captured workflow skill.\n\n"
            f"See SKILL.md for usage instructions.\n"
        ),
    }
