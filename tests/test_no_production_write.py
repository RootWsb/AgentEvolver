"""Critical test: evolution engine must never write to production directory."""

from pathlib import Path

import pytest


@pytest.fixture
def config():
    from agent_evolver.config import get_config
    return get_config()


@pytest.fixture
def path_guard(config):
    from agent_evolver.security.path_guard import assert_candidate_path, is_under_candidate
    return {"assert": assert_candidate_path, "is_under": is_under_candidate}


@pytest.fixture
def patch_ops(config):
    from agent_evolver.engine.patch import fix_skill, create_skill
    return {"fix_skill": fix_skill, "create_skill": create_skill}


def test_path_guard_blocks_production_path(path_guard):
    """path_guard must raise when given a production path."""
    from agent_evolver.config import get_config
    prod_path = get_config().evolver_production_dir / "some-skill"
    assert not path_guard["is_under"](prod_path)
    with pytest.raises(PermissionError):
        path_guard["assert"](prod_path)


def test_path_guard_allows_candidate_path(path_guard):
    """path_guard must allow candidate paths."""
    from agent_evolver.config import get_config
    cand_path = get_config().evolver_candidate_dir / "skills" / "test" / "v0"
    assert path_guard["is_under"](cand_path)
    path_guard["assert"](cand_path)  # should not raise


def test_create_skill_only_writes_candidate(patch_ops, config):
    """create_skill must create files only in candidate directory."""
    # Snapshot production directory
    prod_before = set(config.evolver_production_dir.rglob("*"))

    result = patch_ops["create_skill"](
        skill_name="test-create",
        content={"SKILL.md": "# Test"},
        confidence_score=0.8,
        reason="test",
    )

    assert result["success"] is True
    skill_dir = Path(result["skill_dir"])
    from agent_evolver.security.path_guard import is_under_candidate
    assert is_under_candidate(skill_dir)

    # Production directory must be unchanged
    prod_after = set(config.evolver_production_dir.rglob("*"))
    assert prod_before == prod_after


def test_fix_skill_copies_to_candidate(patch_ops, config):
    """fix_skill copies production to candidate, then only modifies candidate."""
    # Create a fake production skill
    prod_skill_dir = config.evolver_production_dir / "test-fix"
    prod_skill_dir.mkdir(parents=True)
    (prod_skill_dir / "SKILL.md").write_text("# Original")

    # Compute checksum before
    original_content = (prod_skill_dir / "SKILL.md").read_text()

    result = patch_ops["fix_skill"](
        skill_name="test-fix",
        fix_instructions="Fix something",
        confidence_score=0.8,
        reason="test fix",
    )

    assert result["success"] is True
    skill_dir = Path(result["skill_dir"])
    from agent_evolver.security.path_guard import is_under_candidate
    assert is_under_candidate(skill_dir)

    # Production file must be unchanged
    assert (prod_skill_dir / "SKILL.md").read_text() == original_content

    # Candidate must have the PATCH_NOTE
    assert (skill_dir / "PATCH_NOTE.md").exists()

    # mutation.json should exist exactly once (not duplicated)
    assert (skill_dir / "mutation.json").exists()


def test_fix_skill_preserves_subdirectories(patch_ops, config):
    """fix_skill must recursively copy subdirectories to candidate area."""
    # Create production skill with nested structure
    prod_dir = config.evolver_production_dir / "test-nested"
    prod_dir.mkdir(parents=True)
    (prod_dir / "SKILL.md").write_text("# Root")
    (prod_dir / "docs").mkdir()
    (prod_dir / "docs" / "guide.md").write_text("# Guide")
    (prod_dir / "examples").mkdir()
    (prod_dir / "examples" / "demo.py").write_text("print('hello')")

    result = patch_ops["fix_skill"](
        skill_name="test-nested",
        fix_instructions="Fix nested skill",
        confidence_score=0.8,
    )

    assert result["success"] is True
    skill_dir = Path(result["skill_dir"])

    # All files including nested ones must exist in candidate
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "docs" / "guide.md").exists()
    assert (skill_dir / "examples" / "demo.py").exists()
    assert (skill_dir / "docs" / "guide.md").read_text() == "# Guide"


def test_fix_skill_blocks_if_source_missing(patch_ops):
    """fix_skill must fail gracefully if source skill doesn't exist."""
    result = patch_ops["fix_skill"](
        skill_name="nonexistent-skill",
        fix_instructions="Fix something",
        confidence_score=0.8,
    )
    assert result["success"] is False
    assert "not found" in result["error"].lower()
