"""Path validation — ensure all write targets are inside the candidate directory."""

from pathlib import Path

from agent_evolver.config import get_config

_config = get_config()


def is_under_candidate(path: Path | str) -> bool:
    """Return True if path is under the candidate root."""
    try:
        resolved = Path(path).resolve()
        candidate = _config.evolver_candidate_dir.resolve()
        return resolved == candidate or candidate in resolved.parents
    except (OSError, ValueError):
        return False


def assert_candidate_path(path: Path | str) -> None:
    """Raise if path is not under candidate directory."""
    if not is_under_candidate(path):
        raise PermissionError(
            f"Write blocked: {path} is not under candidate directory "
            f"({_config.evolver_candidate_dir}). "
            f"Evolution engine may NOT write to production skill directory."
        )


def get_candidate_skill_dir(skill_name: str, version: int | None = None) -> Path:
    """Return the canonical candidate path for a skill."""
    base = _config.evolver_candidate_dir / "skills" / skill_name
    if version is not None:
        return base / f"v{version}"
    return base
