"""Publisher — the ONLY code path that writes to production skill directory.

This module contains the single approved function for moving a candidate
skill into production. It is called exclusively from the dashboard's
approve endpoint after human review.
"""

from __future__ import annotations

import json
import shutil
import logging
from pathlib import Path
from typing import Any

from agent_evolver.config import get_config
from agent_evolver.engine.candidate_store import (
    CandidateRecord,
    get_candidate,
    update_status,
    archive_rejected,
)
from agent_evolver.engine.types import CandidateStatus
from agent_evolver.protocol.audit import log_publish, log_reject

logger = logging.getLogger("agent_evolver.publisher")

_config = get_config()


def approve(candidate_id: str, approver_id: str = "dashboard") -> dict[str, Any]:
    """Approve a candidate and copy it to production.

    This is the **only** function in the entire codebase that writes
    to the production skill directory. All other code paths are
    blocked by path_guard.py.

    Steps:
        1. Verify candidate exists and is in pending/auto_validated status
        2. Copy candidate files to production directory
        3. Update candidate status to published
        4. Write audit event

    Returns result dict with success flag and details.
    """
    rec = get_candidate(candidate_id)
    if not rec:
        return {"success": False, "error": f"Candidate not found: {candidate_id}"}

    if rec.status not in (CandidateStatus.PENDING.value, CandidateStatus.AUTO_VALIDATED.value):
        return {
            "success": False,
            "error": f"Candidate status is '{rec.status}', cannot approve. "
            f"Expected: pending or auto_validated.",
        }

    candidate_dir = Path(rec.skill_dir_path)
    production_dir = _config.evolver_production_dir / rec.skill_name

    if not candidate_dir.exists():
        return {
            "success": False,
            "error": f"Candidate directory not found: {candidate_dir}",
        }

    # Metadata files that must never be published to production
    _METADATA_FILES = {"mutation.json", "PATCH_NOTE.md", "DERIVATION.md"}

    try:
        # Ensure production directory exists
        production_dir.mkdir(parents=True, exist_ok=True)

        # Copy all files from candidate to production (skip metadata)
        # Use copy2 to preserve metadata; overwrite existing files
        for item in candidate_dir.iterdir():
            if item.name in _METADATA_FILES:
                continue
            dest = production_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Update status
        updated = update_status(
            candidate_id=candidate_id,
            status=CandidateStatus.PUBLISHED.value,
            approver_id=approver_id,
        )

        if not updated:
            return {"success": False, "error": "Failed to update candidate status"}

        # Audit log
        log_publish(
            mutation_id=candidate_id,
            skill_name=rec.skill_name,
            version=rec.version,
            approver_id=approver_id,
            production_path=str(production_dir),
        )

        logger.info(
            "Published candidate %s (skill=%s, v=%d) to %s by %s",
            candidate_id,
            rec.skill_name,
            rec.version,
            production_dir,
            approver_id,
        )

        return {
            "success": True,
            "candidate_id": candidate_id,
            "skill_name": rec.skill_name,
            "version": rec.version,
            "production_path": str(production_dir),
        }

    except Exception as exc:
        logger.exception("Publish failed for candidate %s: %s", candidate_id, exc)
        return {"success": False, "error": str(exc)}


def reject(candidate_id: str, reason: str, approver_id: str = "dashboard") -> dict[str, Any]:
    """Reject a candidate and move it to archive.

    Returns result dict with success flag and details.
    """
    rec = get_candidate(candidate_id)
    if not rec:
        return {"success": False, "error": f"Candidate not found: {candidate_id}"}

    if rec.status != CandidateStatus.PENDING.value:
        return {
            "success": False,
            "error": f"Candidate status is '{rec.status}', cannot reject. "
            f"Expected: pending.",
        }

    # Update status first
    updated = update_status(
        candidate_id=candidate_id,
        status=CandidateStatus.REJECTED.value,
        approver_id=approver_id,
    )

    if not updated:
        return {"success": False, "error": "Failed to update candidate status"}

    # Archive
    archive_dir = archive_rejected(candidate_id)

    # Audit log
    log_reject(
        mutation_id=candidate_id,
        skill_name=rec.skill_name,
        version=rec.version,
        approver_id=approver_id,
        reason=reason,
    )

    logger.info(
        "Rejected candidate %s (skill=%s, v=%d). Reason: %s",
        candidate_id,
        rec.skill_name,
        rec.version,
        reason,
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "skill_name": rec.skill_name,
        "version": rec.version,
        "archive_dir": str(archive_dir) if archive_dir else None,
    }
