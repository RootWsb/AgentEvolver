"""Test candidate skill full lifecycle: create → review → reject → new version."""

from pathlib import Path

import pytest


@pytest.fixture
def store():
    from agent_evolver.engine.candidate_store import (
        create_candidate,
        get_candidate,
        list_candidates,
        update_status,
        get_skill_versions,
    )
    return {
        "create": create_candidate,
        "get": get_candidate,
        "list": list_candidates,
        "update_status": update_status,
        "get_versions": get_skill_versions,
    }


@pytest.fixture
def candidate_status():
    from agent_evolver.engine.types import CandidateStatus
    return CandidateStatus


@pytest.fixture
def path_guard():
    from agent_evolver.security.path_guard import is_under_candidate
    return is_under_candidate


def test_create_candidate(store, path_guard, candidate_status):
    """Creating a candidate sets correct initial state."""
    candidate_id, skill_dir = store["create"](
        skill_name="test-lifecycle",
        evolution_type="fix",
        confidence_score=0.85,
        reason="test creation",
        skill_files={"SKILL.md": "# Test Skill"},
    )

    assert candidate_id.startswith("test-lifecycle~v")
    assert path_guard(skill_dir)

    rec = store["get"](candidate_id)
    assert rec is not None
    assert rec.status == candidate_status.PENDING.value
    assert rec.skill_name == "test-lifecycle"
    assert rec.version == 1
    assert rec.confidence_score == 0.85


def test_list_candidates_by_status(store, candidate_status):
    """list_candidates respects status filter."""
    id1, _ = store["create"](
        skill_name="test-list",
        evolution_type="captured",
        confidence_score=0.7,
        skill_files={"A.md": "a"},
    )
    id2, _ = store["create"](
        skill_name="test-list",
        evolution_type="fix",
        confidence_score=0.8,
        skill_files={"B.md": "b"},
    )

    # Both should be pending
    pending = store["list"](status=candidate_status.PENDING.value)
    ids = [c.candidate_id for c in pending]
    assert id1 in ids
    assert id2 in ids


def test_version_increments(store):
    """Multiple candidates for same skill get incrementing versions."""
    id1, _ = store["create"](
        skill_name="test-version",
        evolution_type="fix",
        confidence_score=0.7,
        skill_files={"v1.md": "1"},
    )
    id2, _ = store["create"](
        skill_name="test-version",
        evolution_type="fix",
        confidence_score=0.8,
        skill_files={"v2.md": "2"},
    )
    id3, _ = store["create"](
        skill_name="test-version",
        evolution_type="captured",
        confidence_score=0.9,
        skill_files={"v3.md": "3"},
    )

    rec1 = store["get"](id1)
    rec2 = store["get"](id2)
    rec3 = store["get"](id3)

    assert rec1.version == 1
    assert rec2.version == 2
    assert rec3.version == 3


def test_get_skill_versions(store):
    """get_skill_versions returns all versions ordered by version desc."""
    # Create our own versions to avoid implicit dependency on other tests
    for i in range(1, 4):
        store["create"](
            skill_name="test-versions-skill",
            evolution_type="fix",
            confidence_score=0.5 + i * 0.1,
            skill_files={f"v{i}.md": str(i)},
        )

    versions = store["get_versions"]("test-versions-skill")
    assert len(versions) == 3
    assert versions[0].version > versions[-1].version


def test_reject_and_archive(store, candidate_status):
    """Rejecting a candidate updates status."""
    candidate_id, skill_dir = store["create"](
        skill_name="test-reject",
        evolution_type="fix",
        confidence_score=0.5,
        skill_files={"SKILL.md": "# Reject Me"},
    )

    store["update_status"](candidate_id, candidate_status.REJECTED.value)

    rec = store["get"](candidate_id)
    assert rec.status == candidate_status.REJECTED.value


def test_mutation_json_written(store):
    """mutation.json should exist in candidate directory."""
    _, skill_dir = store["create"](
        skill_name="test-mutation",
        evolution_type="captured",
        confidence_score=0.9,
        skill_files={"SKILL.md": "# Skill"},
        mutation_dict={"test": "mutation"},
    )

    mutation_path = skill_dir / "mutation.json"
    assert mutation_path.exists()
    import json

    data = json.loads(mutation_path.read_text())
    assert data["test"] == "mutation"

    # Should be written exactly once
    content = mutation_path.read_text()
    assert content.count('"test"') == 1
