"""Diff engine — compare production skill files with candidate versions."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from agent_evolver.config import get_config

_config = get_config()


def compute_diff(
    skill_name: str,
    candidate_dir: Path,
    production_dir: Path | None = None,
) -> dict[str, Any]:
    """Compute unified diff between production and candidate skill files.

    Returns dict with:
        - files: list of file diff entries
        - new_files: files only in candidate
        - removed_files: files only in production
    """
    if production_dir is None:
        production_dir = _config.evolver_production_dir / skill_name

    prod_files = _list_text_files(production_dir) if production_dir.exists() else {}
    cand_files = _list_text_files(candidate_dir) if candidate_dir.exists() else {}

    all_filenames = set(prod_files.keys()) | set(cand_files.keys())

    result = {
        "skill_name": skill_name,
        "production_dir": str(production_dir),
        "candidate_dir": str(candidate_dir),
        "files": [],
        "new_files": [],
        "removed_files": [],
    }

    for filename in sorted(all_filenames):
        prod_path = prod_files.get(filename)
        cand_path = cand_files.get(filename)

        if prod_path and cand_path:
            # Both exist — compute diff
            prod_lines = prod_path.read_text(encoding="utf-8").splitlines(keepends=True)
            cand_lines = cand_path.read_text(encoding="utf-8").splitlines(keepends=True)

            # Ensure lines end with newline for clean diff
            if prod_lines and not prod_lines[-1].endswith("\n"):
                prod_lines[-1] += "\n"
            if cand_lines and not cand_lines[-1].endswith("\n"):
                cand_lines[-1] += "\n"

            diff_lines = list(
                difflib.unified_diff(
                    prod_lines,
                    cand_lines,
                    fromfile=f"a/{filename}",
                    tofile=f"b/{filename}",
                )
            )

            result["files"].append({
                "filename": filename,
                "status": "modified",
                "diff": "".join(diff_lines),
                "added_lines": _count_added(diff_lines),
                "removed_lines": _count_removed(diff_lines),
            })

        elif cand_path:
            # Only in candidate
            content = cand_path.read_text(encoding="utf-8")
            result["new_files"].append({
                "filename": filename,
                "content": content,
                "line_count": len(content.splitlines()),
            })

        else:
            # Only in production (removed in candidate)
            result["removed_files"].append({
                "filename": filename,
            })

    return result


# Metadata files that exist only in candidate area and should not appear in diffs
_METADATA_FILES = {"mutation.json", "PATCH_NOTE.md", "DERIVATION.md"}


def _list_text_files(directory: Path) -> dict[str, Path]:
    """Return mapping of relative path -> absolute path for text files."""
    files = {}
    if not directory.exists():
        return files
    for path in directory.rglob("*"):
        if path.is_file() and path.name not in _METADATA_FILES and _is_text_file(path):
            rel = path.relative_to(directory).as_posix()
            files[rel] = path
    return files


def _is_text_file(path: Path, max_binary_check: int = 8192) -> bool:
    """Heuristic: check if file is text (not binary)."""
    try:
        with path.open("rb") as f:
            chunk = f.read(max_binary_check)
        # Check for null bytes (common binary indicator)
        if b"\x00" in chunk:
            return False
        # Try decode as UTF-8
        chunk.decode("utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        return False


def _count_added(diff_lines: list[str]) -> int:
    """Count added lines in unified diff (lines starting with + but not +++)."""
    return sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))


def _count_removed(diff_lines: list[str]) -> int:
    """Count removed lines in unified diff (lines starting with - but not ---)."""
    return sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
