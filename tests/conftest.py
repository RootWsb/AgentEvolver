"""Shared pytest fixtures."""

import os
import pytest

from agent_evolver.config import _reset_config


@pytest.fixture(autouse=True)
def isolate_evolver_env(tmp_path, monkeypatch):
    """Reset config singleton and point all paths to temp dirs for each test."""
    candidate_dir = tmp_path / "candidate"
    audit_dir = tmp_path / "audit"
    production_dir = tmp_path / "production"
    candidate_dir.mkdir()
    audit_dir.mkdir()
    production_dir.mkdir()

    monkeypatch.setenv("EVOLVER_CANDIDATE_DIR", str(candidate_dir))
    monkeypatch.setenv("EVOLVER_AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("EVOLVER_PRODUCTION_DIR", str(production_dir))
    monkeypatch.setenv("EVOLVER_UPSTREAM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("EVOLVER_UPSTREAM_API_KEY", "sk-test123")
    monkeypatch.setenv("EVOLVER_UPSTREAM_MODEL", "gpt-4o")

    # Reset the config singleton so it re-reads env vars
    _reset_config()

    # Reset candidate store engine so it picks up the new DB path
    from agent_evolver.engine.candidate_store import reset_candidate_engine
    reset_candidate_engine()

    # Reset storage engine so it picks up the new DB path
    from agent_evolver.storage.db import reset_storage_engine
    reset_storage_engine()

    yield

    # _reset_config again to prevent cross-test leakage
    _reset_config()
    reset_candidate_engine()
    reset_storage_engine()
