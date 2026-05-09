"""Append-only audit log in JSONL format."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_evolver.config import get_config

_config = get_config()


def _compute_hash(line: str, prev_hash: str = "") -> str:
    """Compute chained hash for tamper evidence."""
    return hashlib.sha256(f"{prev_hash}:{line}".encode()).hexdigest()[:16]


def _read_last_hash(log_path: Path) -> str:
    """Read the last hash from the audit log."""
    if not log_path.exists():
        return ""
    try:
        with log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                return ""
            last = json.loads(lines[-1])
            return last.get("_hash", "")
    except (json.JSONDecodeError, KeyError):
        return ""


def append_audit_event(
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Append a single event to the audit log.

    Each line is a JSON object with:
    - ts: ISO timestamp
    - type: event type
    - payload: arbitrary data
    - _hash: chained hash for tamper evidence
    """
    log_path = _config.audit_events_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    prev_hash = _read_last_hash(log_path)

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "payload": payload,
    }

    line = json.dumps(event, ensure_ascii=False)
    event["_hash"] = _compute_hash(line, prev_hash)

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_evolution(
    mutation_id: str,
    skill_name: str,
    version: int,
    evolution_type: str,
    confidence: float,
    candidate_path: str,
) -> None:
    """Log an evolution event."""
    append_audit_event("evolution", {
        "mutation_id": mutation_id,
        "skill_name": skill_name,
        "version": version,
        "evolution_type": evolution_type,
        "confidence": confidence,
        "candidate_path": candidate_path,
    })


def log_publish(
    mutation_id: str,
    skill_name: str,
    version: int,
    approver_id: str,
    production_path: str,
) -> None:
    """Log a publish (approval) event."""
    append_audit_event("publish", {
        "mutation_id": mutation_id,
        "skill_name": skill_name,
        "version": version,
        "approver_id": approver_id,
        "production_path": production_path,
    })


def log_reject(
    mutation_id: str,
    skill_name: str,
    version: int,
    approver_id: str,
    reason: str,
) -> None:
    """Log a rejection event."""
    append_audit_event("reject", {
        "mutation_id": mutation_id,
        "skill_name": skill_name,
        "version": version,
        "approver_id": approver_id,
        "reason": reason,
    })
