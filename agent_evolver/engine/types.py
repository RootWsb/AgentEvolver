"""Core types for the evolution engine (simplified from OpenSpace)."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EvolutionType(Enum):
    """Three modes of evolution."""

    FIX = "fix"
    DERIVED = "derived"
    CAPTURED = "captured"

    def to_origin(self) -> str:
        return {
            EvolutionType.FIX: "fixed",
            EvolutionType.DERIVED: "derived",
            EvolutionType.CAPTURED: "captured",
        }[self]


class SkillCategory(Enum):
    """Skill classification."""

    TOOL_GUIDE = "tool_guide"
    WORKFLOW = "workflow"
    REFERENCE = "reference"


class SkillVisibility(Enum):
    """Skill visibility level."""

    PRIVATE = "private"
    PUBLIC = "public"


class CandidateStatus(Enum):
    """Lifecycle status of a candidate skill."""

    PENDING = "pending"
    AUTO_VALIDATED = "auto_validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


@dataclass
class SkillLineage:
    """Lineage metadata for a skill."""

    origin: str = "imported"
    generation: int = 0
    parent_skill_ids: list[str] = field(default_factory=list)
    source_task_id: str | None = None
    change_summary: str = ""
    content_diff: str = ""
    content_snapshot: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    created_by: str = "agent-evolver"


@dataclass
class SkillRecord:
    """A skill as stored in the candidate store."""

    skill_id: str
    name: str
    description: str = ""
    path: str = ""
    is_active: bool = True
    category: SkillCategory = SkillCategory.WORKFLOW
    visibility: SkillVisibility = SkillVisibility.PRIVATE
    creator_id: str = ""
    lineage: SkillLineage = field(default_factory=SkillLineage)
    total_selections: int = 0
    total_applied: int = 0
    total_completions: int = 0
    total_fallbacks: int = 0
    recent_analyses: list[dict[str, Any]] = field(default_factory=list)
    first_seen: str = ""
    last_updated: str = ""

    @property
    def applied_rate(self) -> float:
        return self.total_applied / self.total_selections if self.total_selections > 0 else 0.0

    @property
    def completion_rate(self) -> float:
        return (
            self.total_completions / self.total_applied if self.total_applied > 0 else 0.0
        )

    @property
    def fallback_rate(self) -> float:
        return (
            self.total_fallbacks / self.total_applied if self.total_applied > 0 else 0.0
        )

    @property
    def effective_rate(self) -> float:
        return self.completion_rate * (1 - self.fallback_rate)


@dataclass
class EvolutionSuggestion:
    """A suggestion from the analyzer to evolve one or more skills."""

    evolution_type: EvolutionType
    target_skill_ids: list[str] = field(default_factory=list)
    category: SkillCategory = SkillCategory.WORKFLOW
    direction: str = ""  # "fix", "improve", "specialize", "generalize"
    confidence: float = 0.0
    reason: str = ""


@dataclass
class SkillJudgment:
    """Per-skill judgment within an execution analysis."""

    skill_id: str
    skill_applied: bool = False
    note: str = ""


@dataclass
class ExecutionAnalysis:
    """Result of analyzing a completed session."""

    task_id: str
    timestamp: str = ""
    task_completed: bool = False
    execution_note: str = ""
    tool_issues: list[str] = field(default_factory=list)
    skill_judgments: list[SkillJudgment] = field(default_factory=list)
    evolution_suggestions: list[EvolutionSuggestion] = field(default_factory=list)
    cross_session_evidence: dict[str, Any] = field(default_factory=dict)
    analyzed_by: str = "agent-evolver"
    analyzed_at: str = ""


@dataclass
class SkillEditResult:
    """Result of applying a patch to a skill."""

    success: bool = False
    error: str | None = None
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
