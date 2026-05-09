"""Test cross-session semantic pattern mining."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session as DBSession

from agent_evolver.engine.types import EvolutionType
from agent_evolver.storage.db import StorageSessionLocal, init_storage_db
from agent_evolver.storage.models import PatternOccurrence, Session, Message, ToolCall
from agent_evolver.storage.pattern_store import (
    compute_pattern_hash,
    record_pattern_occurrence,
    get_pattern_stats,
    mark_pattern_captured,
)
from agent_evolver.storage.semantic_queries import (
    find_similar_sessions,
    find_recurring_tool_sequences,
    find_message_patterns,
)
from agent_evolver.storage.session_store import (
    create_session,
    add_message,
    add_tool_call,
)


@pytest.fixture
def db() -> DBSession:
    """Provide a clean storage DB session with tables initialized."""
    init_storage_db()
    session = StorageSessionLocal()
    yield session
    session.close()


def _make_completed_session(
    db: DBSession,
    session_id: str,
    task_desc: str,
    agent_id: str = "test-agent",
) -> Session:
    """Helper: create a completed session with task_desc."""
    sess = create_session(
        db=db,
        session_id=session_id,
        agent_id=agent_id,
        task_desc=task_desc,
    )
    # Mark as completed
    from agent_evolver.storage.session_store import update_session_status
    update_session_status(db, session_id, "completed", total_tokens=100)
    return sess


class TestSimilarSessionsQuery:
    """FTS5 / LIKE fallback finds similar completed sessions."""

    def test_like_fallback_finds_similar_sessions(self, db):
        """Without FTS5, LIKE fallback should find matching sessions."""
        # Create sessions: 2 about deployment, 1 about data analysis
        _make_completed_session(db, "sess-deploy-1", "deploy docker container to production")
        _make_completed_session(db, "sess-deploy-2", "deploy app using docker compose")
        _make_completed_session(db, "sess-data-1", "analyze sales data with pandas")

        # Search for deployment-related sessions
        results = find_similar_sessions(
            task_description="deploy docker container",
            db=db,
        )

        # Should find the 2 deployment sessions
        assert len(results) >= 2
        ids = {r["id"] for r in results}
        assert "sess-deploy-1" in ids
        assert "sess-deploy-2" in ids
        # Data analysis session should not match
        assert "sess-data-1" not in ids

    def test_only_completed_sessions_returned(self, db):
        """Failed/in-progress sessions should not appear in results."""
        _make_completed_session(db, "sess-ok", "deploy docker container")

        # Create a failed session
        sess_fail = create_session(db, "sess-fail", task_desc="deploy docker container")
        from agent_evolver.storage.session_store import update_session_status
        update_session_status(db, "sess-fail", "failed")

        results = find_similar_sessions(task_description="deploy docker", db=db)
        ids = {r["id"] for r in results}
        assert "sess-ok" in ids
        assert "sess-fail" not in ids

    def test_empty_result_for_no_match(self, db):
        """No matching sessions returns empty list."""
        _make_completed_session(db, "sess-1", "deploy app")
        results = find_similar_sessions(task_description="quantum physics", db=db)
        assert results == []


class TestRecurringToolSequences:
    """Detect tool sequences that repeat across sessions."""

    def test_finds_recurring_sequence(self, db):
        """A tool sequence appearing in 3+ sessions is detected."""
        # Create 3 sessions with identical tool sequences
        for i in range(3):
            sid = f"sess-seq-{i}"
            _make_completed_session(db, sid, "deploy service")
            add_tool_call(db, sid, "docker_build", {}, "ok", "success")
            add_tool_call(db, sid, "docker_push", {}, "ok", "success")
            add_tool_call(db, sid, "kubectl_apply", {}, "ok", "success")

        session_ids = [f"sess-seq-{i}" for i in range(3)]
        results = find_recurring_tool_sequences(
            session_ids=session_ids,
            min_occurrences=3,
            db=db,
        )

        assert len(results) >= 1
        seq = results[0]
        assert seq["sequence"] == ["docker_build", "docker_push", "kubectl_apply"]
        assert seq["unique_sessions"] >= 3

    def test_no_result_below_threshold(self, db):
        """Sequences appearing in fewer sessions than threshold are ignored."""
        for i in range(2):
            sid = f"sess-below-{i}"
            _make_completed_session(db, sid, "deploy service")
            add_tool_call(db, sid, "tool_a", {}, "ok", "success")

        session_ids = [f"sess-below-{i}" for i in range(2)]
        results = find_recurring_tool_sequences(
            session_ids=session_ids,
            min_occurrences=3,
            db=db,
        )
        assert results == []

    def test_error_tools_excluded(self, db):
        """Failed tool calls should not be included in sequences."""
        for i in range(3):
            sid = f"sess-err-{i}"
            _make_completed_session(db, sid, "deploy service")
            add_tool_call(db, sid, "tool_ok", {}, "ok", "success")
            add_tool_call(db, sid, "tool_fail", {}, "err", "error")

        session_ids = [f"sess-err-{i}" for i in range(3)]
        results = find_recurring_tool_sequences(
            session_ids=session_ids,
            min_occurrences=3,
            db=db,
        )
        # Only tool_ok should appear in sequences
        for r in results:
            assert "tool_fail" not in r["sequence"]


class TestMessagePatterns:
    """Detect recurring message content patterns."""

    def test_finds_recurring_ngrams(self, db):
        """Common phrases across assistant messages are detected."""
        _make_completed_session(db, "sess-msg-1", "test task")
        _make_completed_session(db, "sess-msg-2", "test task")
        _make_completed_session(db, "sess-msg-3", "test task")

        for i in range(1, 4):
            add_message(
                db,
                f"sess-msg-{i}",
                "assistant",
                "The deployment was successful. You can now verify the service.",
            )

        results = find_message_patterns(
            session_ids=["sess-msg-1", "sess-msg-2", "sess-msg-3"],
            role="assistant",
            min_occurrences=3,
            db=db,
        )

        assert len(results) >= 1
        # Should find phrases like "deployment was successful"
        patterns = [r["pattern"] for r in results]
        assert any("deployment" in p for p in patterns)


class TestPatternStore:
    """Pattern occurrence recording and statistics."""

    def test_compute_pattern_hash_is_stable(self):
        """Same input always produces same hash."""
        h1 = compute_pattern_hash("tool_sequence", {"seq": ["a", "b"]})
        h2 = compute_pattern_hash("tool_sequence", {"seq": ["a", "b"]})
        assert h1 == h2
        assert len(h1) == 32

    def test_different_inputs_different_hashes(self):
        """Different inputs produce different hashes."""
        h1 = compute_pattern_hash("type_a", {"data": 1})
        h2 = compute_pattern_hash("type_b", {"data": 1})
        assert h1 != h2

    def test_record_and_retrieve_pattern(self, db):
        """Recorded patterns can be queried for stats."""
        _make_completed_session(db, "sess-001", "deploy app")
        pattern_hash = record_pattern_occurrence(
            pattern_type="tool_sequence",
            pattern_data={"seq": ["build", "push"]},
            session_id="sess-001",
            similarity_score=0.85,
            db=db,
        )

        stats = get_pattern_stats(pattern_hash, min_similarity=0.7, db=db)
        assert stats["total_occurrences"] == 1
        assert stats["unique_sessions"] == 1
        assert stats["avg_similarity"] == pytest.approx(0.85, rel=1e-3)
        assert stats["captured_as_skill"] is None

    def test_multiple_occurrences_aggregate(self, db):
        """Multiple occurrences of same pattern are aggregated."""
        data = {"seq": ["build", "test"]}

        for i in range(3):
            _make_completed_session(db, f"sess-{i}", "deploy app")
            record_pattern_occurrence(
                pattern_type="tool_sequence",
                pattern_data=data,
                session_id=f"sess-{i}",
                similarity_score=0.8 + i * 0.05,
                db=db,
            )

        pattern_hash = compute_pattern_hash("tool_sequence", data)
        stats = get_pattern_stats(pattern_hash, min_similarity=0.7, db=db)

        assert stats["total_occurrences"] == 3
        assert stats["unique_sessions"] == 3
        assert stats["avg_similarity"] == pytest.approx(0.85, rel=1e-3)

    def test_mark_pattern_captured(self, db):
        """mark_pattern_captured updates captured_as_skill field."""
        data = {"seq": ["deploy"]}
        pattern_hash = compute_pattern_hash("tool_sequence", data)

        for i in range(2):
            _make_completed_session(db, f"sess-c-{i}", "deploy app")
            record_pattern_occurrence(
                pattern_type="tool_sequence",
                pattern_data=data,
                session_id=f"sess-c-{i}",
                similarity_score=0.9,
                db=db,
            )

        updated = mark_pattern_captured(pattern_hash, "candidate-123", db=db)
        assert updated == 2

        stats = get_pattern_stats(pattern_hash, db=db)
        assert stats["captured_as_skill"] == "candidate-123"

    def test_stats_respects_min_similarity(self, db):
        """Stats filtered by minimum similarity threshold."""
        data = {"seq": ["test"]}
        pattern_hash = compute_pattern_hash("tool_sequence", data)

        _make_completed_session(db, "sess-high", "deploy app")
        _make_completed_session(db, "sess-low", "deploy app")

        record_pattern_occurrence(
            "tool_sequence", data, "sess-high", 0.9, db=db,
        )
        record_pattern_occurrence(
            "tool_sequence", data, "sess-low", 0.5, db=db,
        )

        stats_high = get_pattern_stats(pattern_hash, min_similarity=0.8, db=db)
        assert stats_high["total_occurrences"] == 1

        stats_all = get_pattern_stats(pattern_hash, min_similarity=0.0, db=db)
        assert stats_all["total_occurrences"] == 2


class TestAnalyzerCrossSessionBoost:
    """Analyzer applies cross-session confidence boost."""

    def test_captured_confidence_boosted_with_patterns(self, db):
        """When recurring patterns exist, CAPTURED confidence gets boosted."""
        from agent_evolver.engine.analyzer import analyze_session

        # Create 3 similar sessions with recurring tool sequences
        for i in range(3):
            sid = f"sess-boost-{i}"
            _make_completed_session(db, sid, "deploy docker container to production")
            add_tool_call(db, sid, "docker_build", {}, "ok", "success")
            add_tool_call(db, sid, "docker_push", {}, "ok", "success")

        # Analyze a new session with the same task description
        new_sid = "sess-boost-new"
        _make_completed_session(db, new_sid, "deploy docker container to production")
        add_tool_call(db, new_sid, "docker_build", {}, "ok", "success")

        analysis = analyze_session(db, new_sid, task_completed=True)

        captured = [
            s for s in analysis.evolution_suggestions
            if s.evolution_type == EvolutionType.CAPTURED
        ]

        if captured:
            # Confidence should be boosted above baseline 0.6
            assert captured[0].confidence > 0.6
            assert "Cross-session validation" in captured[0].reason
            assert analysis.cross_session_evidence
            assert analysis.cross_session_evidence.get("similar_session_count", 0) > 0

    def test_no_boost_without_similar_sessions(self, db):
        """Without similar sessions, CAPTURED stays at baseline confidence."""
        from agent_evolver.engine.analyzer import analyze_session

        sid = "sess-noboost"
        _make_completed_session(db, sid, "unique quantum computing task xyz")
        add_tool_call(db, sid, "tool_a", {}, "ok", "success")

        analysis = analyze_session(db, sid, task_completed=True)

        captured = [
            s for s in analysis.evolution_suggestions
            if s.evolution_type == EvolutionType.CAPTURED
        ]

        if captured:
            # Baseline confidence without boost
            assert captured[0].confidence == 0.6

    def test_cross_session_evidence_structure(self, db):
        """cross_session_evidence has expected fields."""
        from agent_evolver.engine.analyzer import analyze_session

        for i in range(3):
            sid = f"sess-ev-{i}"
            _make_completed_session(db, sid, "deploy app to kubernetes")
            add_tool_call(db, sid, "kubectl", {}, "ok", "success")

        analysis = analyze_session(db, "sess-ev-0", task_completed=True)

        assert "similar_session_count" in analysis.cross_session_evidence
        assert "recurring_patterns" in analysis.cross_session_evidence
        assert "confidence_boost" in analysis.cross_session_evidence
