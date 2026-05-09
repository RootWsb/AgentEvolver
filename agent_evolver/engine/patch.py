"""Skill patch operations — all writes are redirected to candidate directory.

This is the single chokepoint for all disk writes from the evolution engine.
The three public entrypoints are:
  - fix_skill:   copy production skill → candidate, then apply fixes
  - derive_skill: create derived skill in candidate area
  - create_skill: create new skill in candidate area
"""

from pathlib import Path
from typing import Any

from agent_evolver.config import get_config
from agent_evolver.engine.candidate_store import create_candidate
from agent_evolver.engine.types import EvolutionType
from agent_evolver.protocol.mutation import create_mutation

_config = get_config()


def _read_dir_files(dir_path: Path) -> dict[str, str]:
    """Recursively read all text files under dir_path into a flat dict.

    Keys are relative POSIX paths (e.g. "docs/README.md").
    """
    files: dict[str, str] = {}
    if not dir_path.exists():
        return files
    for file_path in dir_path.rglob("*"):
        if file_path.is_file():
            rel = file_path.relative_to(dir_path).as_posix()
            try:
                files[rel] = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                # Skip binary or unreadable files
                continue
    return files


def fix_skill(
    skill_name: str,
    fix_instructions: str,
    original_skill_dir: Path | None = None,
    confidence_score: float = 0.0,
    reason: str = "",
) -> dict[str, Any]:
    """Fix an existing skill by copying it to candidate area and applying patches.

    Returns dict with candidate_id, skill_dir, files_modified.
    """
    # Determine source directory
    if original_skill_dir is None:
        original_skill_dir = _config.evolver_production_dir / skill_name

    if not original_skill_dir.exists():
        return {
            "success": False,
            "error": f"Source skill directory not found: {original_skill_dir}",
        }

    # Compute next version (passed to create_candidate so it's only calculated once)
    from agent_evolver.engine.candidate_store import _next_version, _get_session_local

    db = _get_session_local()()
    try:
        version = _next_version(skill_name, db)
    finally:
        db.close()

    # Recursively read all source files (including subdirectories)
    skill_files = _read_dir_files(original_skill_dir)

    # Apply fix note
    patch_note = (
        f"# Fix Instructions\n\n{fix_instructions}\n\n"
        f"_Applied to version {version}_\n"
    )
    skill_files["PATCH_NOTE.md"] = patch_note
    files_modified = ["PATCH_NOTE.md"]

    # Create mutation record
    mutation = create_mutation(
        evolution_type=EvolutionType.FIX,
        target_skill_name=skill_name,
        version=version,
        parent_version=version - 1 if version > 1 else None,
        confidence_score=confidence_score,
        reason=reason,
        files_modified=files_modified,
    )

    # Single write point: create_candidate handles all disk I/O
    candidate_id, skill_dir = create_candidate(
        skill_name=skill_name,
        evolution_type=EvolutionType.FIX.value,
        confidence_score=confidence_score,
        reason=reason,
        skill_files=skill_files,
        mutation_dict=mutation.to_dict(),
        version=version,
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "skill_dir": str(skill_dir),
        "version": version,
        "files_modified": files_modified,
    }


def derive_skill(
    source_skill_names: list[str],
    new_skill_name: str,
    derive_instructions: str,
    source_dirs: list[Path] | None = None,
    confidence_score: float = 0.0,
    reason: str = "",
) -> dict[str, Any]:
    """Derive a new skill by combining existing skills.

    Returns dict with candidate_id, skill_dir, files_created.
    """
    if not source_skill_names:
        return {
            "success": False,
            "error": "At least one source skill name is required",
        }

    if source_dirs is None:
        source_dirs = [_config.evolver_production_dir / name for name in source_skill_names]

    # Verify sources exist
    for src_dir in source_dirs:
        if not src_dir.exists():
            return {
                "success": False,
                "error": f"Source skill directory not found: {src_dir}",
            }

    version = 0  # New skill starts at v0

    # Recursively read all source files (later sources overwrite earlier ones on name clash)
    skill_files: dict[str, str] = {}
    files_created = []
    for src_dir in source_dirs:
        src_files = _read_dir_files(src_dir)
        skill_files.update(src_files)
        files_created.extend(src_files.keys())

    # Write derivation note
    skill_files["DERIVATION.md"] = (
        f"# Derivation\n\n"
        f"Derived from: {', '.join(source_skill_names)}\n\n"
        f"Instructions: {derive_instructions}\n\n"
    )
    files_created.append("DERIVATION.md")

    # Create mutation
    mutation = create_mutation(
        evolution_type=EvolutionType.DERIVED,
        target_skill_name=new_skill_name,
        version=version,
        confidence_score=confidence_score,
        reason=reason,
        files_created=files_created,
    )

    # Single write point
    candidate_id, skill_dir = create_candidate(
        skill_name=new_skill_name,
        evolution_type=EvolutionType.DERIVED.value,
        confidence_score=confidence_score,
        reason=reason,
        skill_files=skill_files,
        mutation_dict=mutation.to_dict(),
        version=version,
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "skill_dir": str(skill_dir),
        "version": version,
        "files_created": files_created,
    }


def create_skill(
    skill_name: str,
    content: dict[str, str],
    confidence_score: float = 0.0,
    reason: str = "",
) -> dict[str, Any]:
    """Create a brand new skill from scratch in candidate area.

    Args:
        skill_name: Name of the new skill
        content: Dict mapping filename → file content
        confidence_score: Evolution confidence (0.0-1.0)
        reason: Why this skill was created

    Returns dict with candidate_id, skill_dir, files_created.
    """
    version = 0
    files_created = list(content.keys())

    # Create mutation
    mutation = create_mutation(
        evolution_type=EvolutionType.CAPTURED,
        target_skill_name=skill_name,
        version=version,
        confidence_score=confidence_score,
        reason=reason,
        files_created=files_created,
    )

    # Single write point
    candidate_id, skill_dir = create_candidate(
        skill_name=skill_name,
        evolution_type=EvolutionType.CAPTURED.value,
        confidence_score=confidence_score,
        reason=reason,
        skill_files=content,
        mutation_dict=mutation.to_dict(),
        version=version,
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "skill_dir": str(skill_dir),
        "version": version,
        "files_created": files_created,
    }
