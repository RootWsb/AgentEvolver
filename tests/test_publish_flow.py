"""Test the publish flow: candidate → approval → production + audit log."""

from pathlib import Path

import pytest


@pytest.fixture
def config():
    from agent_evolver.config import get_config
    return get_config()


@pytest.fixture
def store():
    from agent_evolver.engine.candidate_store import create_candidate, get_candidate
    from agent_evolver.engine.types import CandidateStatus
    return {
        "create": create_candidate,
        "get": get_candidate,
        "status": CandidateStatus,
    }


@pytest.fixture
def publisher():
    from agent_evolver.dashboard.publisher import approve, reject
    return {"approve": approve, "reject": reject}


def test_approve_publishes_to_production(store, publisher, config):
    """Approving a candidate copies files to production directory."""
    candidate_id, skill_dir = store["create"](
        skill_name="test-publish",
        evolution_type="fix",
        confidence_score=0.9,
        reason="Ready for production",
        skill_files={
            "SKILL.md": "# Published Skill\n\nThis is the content.",
            "README.md": "# README",
        },
    )

    # Pre-conditions
    prod_skill_dir = config.evolver_production_dir / "test-publish"
    assert not prod_skill_dir.exists() or not (prod_skill_dir / "SKILL.md").exists()

    # Approve
    result = publisher["approve"](candidate_id, approver_id="test-user")

    assert result["success"] is True
    assert result["skill_name"] == "test-publish"
    assert result["production_path"] == str(prod_skill_dir)

    # Production directory must now have the files
    assert (prod_skill_dir / "SKILL.md").exists()
    assert (prod_skill_dir / "README.md").exists()
    content = (prod_skill_dir / "SKILL.md").read_text()
    assert "Published Skill" in content

    # Status must be published
    rec = store["get"](candidate_id)
    assert rec.status == store["status"].PUBLISHED.value
    assert rec.approver_id == "test-user"


def test_approve_is_idempotent_guard(store, publisher):
    """Approving an already-published candidate should fail."""
    candidate_id, _ = store["create"](
        skill_name="test-idempotent",
        evolution_type="captured",
        confidence_score=0.8,
        skill_files={"SKILL.md": "# Content"},
    )

    # First approve succeeds
    result1 = publisher["approve"](candidate_id)
    assert result1["success"] is True

    # Second approve fails
    result2 = publisher["approve"](candidate_id)
    assert result2["success"] is False
    assert "published" in result2["error"].lower() or "status" in result2["error"].lower()


def test_reject_archives_candidate(store, publisher):
    """Rejecting a candidate updates status."""
    candidate_id, skill_dir = store["create"](
        skill_name="test-reject-flow",
        evolution_type="fix",
        confidence_score=0.3,
        reason="Low confidence",
        skill_files={"SKILL.md": "# Rejected"},
    )

    result = publisher["reject"](candidate_id, reason="Not good enough", approver_id="reviewer")

    assert result["success"] is True
    rec = store["get"](candidate_id)
    assert rec.status == store["status"].REJECTED.value


def test_approve_nonexistent_fails(publisher):
    """Approving a non-existent candidate returns error."""
    result = publisher["approve"]("nonexistent~v1~abc123")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_audit_log_written(store, publisher, config):
    """Approval writes to audit events file."""
    candidate_id, _ = store["create"](
        skill_name="test-audit",
        evolution_type="captured",
        confidence_score=0.9,
        skill_files={"SKILL.md": "# Audit"},
    )
    publisher["approve"](candidate_id)

    # Find the audit file
    audit_path = config.audit_events_path
    assert audit_path.exists()
    lines = audit_path.read_text().strip().split("\n")
    # At least one publish event should exist
    import json

    events = [json.loads(line) for line in lines if line.strip()]
    publish_events = [e for e in events if e.get("type") == "publish"]
    assert len(publish_events) >= 1

    # Verify hash chain
    for event in events:
        assert "_hash" in event
        assert len(event["_hash"]) == 16  # truncated SHA256
