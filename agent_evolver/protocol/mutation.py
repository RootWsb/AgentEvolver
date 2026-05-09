"""Mutation object — every evolution produces one of these."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_evolver.engine.types import EvolutionType


@dataclass
class Mutation:
    """An explicit, auditable record of a single evolution step."""

    mutation_id: str
    evolution_type: str
    target_skill_name: str
    version: int
    parent_version: int | None = None
    trigger_type: str = "task_post"
    strategy_preset: str = "balanced"
    confidence_score: float = 0.0
    signal_hash: str = ""
    reason: str = ""
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def write(self, output_dir: Path) -> Path:
        """Write mutation.json to the candidate directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "mutation.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def create_mutation(
    evolution_type: EvolutionType,
    target_skill_name: str,
    version: int,
    parent_version: int | None = None,
    trigger_type: str = "task_post",
    strategy_preset: str = "balanced",
    confidence_score: float = 0.0,
    signal_hash: str = "",
    reason: str = "",
    files_modified: list[str] | None = None,
    files_created: list[str] | None = None,
) -> Mutation:
    """Factory for creating a Mutation with auto-generated ID."""
    import uuid

    return Mutation(
        mutation_id=str(uuid.uuid4()),
        evolution_type=evolution_type.value,
        target_skill_name=target_skill_name,
        version=version,
        parent_version=parent_version,
        trigger_type=trigger_type,
        strategy_preset=strategy_preset,
        confidence_score=confidence_score,
        signal_hash=signal_hash,
        reason=reason,
        files_modified=files_modified or [],
        files_created=files_created or [],
    )
