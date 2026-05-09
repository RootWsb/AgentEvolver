"""Dashboard backend — FastAPI routes for candidate review and approval."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_evolver.config import get_config
from agent_evolver.dashboard.diff_engine import compute_diff
from agent_evolver.dashboard.publisher import approve, reject
from agent_evolver.engine.candidate_store import (
    CandidateRecord,
    get_candidate,
    init_candidate_db,
    list_candidates,
    get_skill_versions,
)
from agent_evolver.engine.types import CandidateStatus
from agent_evolver.storage.queries import get_metric_summary
from agent_evolver.storage.db import get_storage_session, init_storage_db
import uvicorn

_config = get_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init storage and candidate DB tables."""
    init_storage_db()
    init_candidate_db()
    yield


app = FastAPI(
    title="Agent Evolver Dashboard",
    description="Review and approve evolved skills",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend on different port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──

class CandidateOut(BaseModel):
    candidate_id: str
    skill_name: str
    version: int
    status: str
    evolution_type: str
    confidence_score: float
    reason: str | None
    created_at: str
    skill_dir_path: str

    @classmethod
    def from_record(cls, rec: CandidateRecord) -> "CandidateOut":
        return cls(
            candidate_id=rec.candidate_id,
            skill_name=rec.skill_name,
            version=rec.version,
            status=rec.status,
            evolution_type=rec.evolution_type,
            confidence_score=rec.confidence_score,
            reason=rec.reason,
            created_at=rec.created_at.isoformat() if rec.created_at else "",
            skill_dir_path=rec.skill_dir_path,
        )


class CrossSessionValidation(BaseModel):
    similar_sessions_found: int
    recurring_patterns: list[dict[str, Any]]
    statistical_confidence_boost: float


class CandidateDetailOut(CandidateOut):
    cross_session_validation: CrossSessionValidation | None = None


class ApproveRequest(BaseModel):
    approver_id: str = "dashboard"


class RejectRequest(BaseModel):
    reason: str
    approver_id: str = "dashboard"


class DiffResponse(BaseModel):
    skill_name: str
    production_dir: str
    candidate_dir: str
    files: list[dict[str, Any]]
    new_files: list[dict[str, Any]]
    removed_files: list[dict[str, Any]]


# ── Routes ──

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/candidates")
async def get_candidates(
    skill_name: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[CandidateOut]:
    """List candidates with optional filters."""
    records = list_candidates(
        skill_name=skill_name,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [CandidateOut.from_record(r) for r in records]


@app.get("/api/candidates/{candidate_id}")
async def get_candidate_detail(candidate_id: str) -> CandidateDetailOut:
    """Get a single candidate by ID with cross-session validation evidence."""
    rec = get_candidate(candidate_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Candidate not found")

    base = CandidateOut.from_record(rec)

    # Try to load cross-session evidence from mutation.json
    cross_session: CrossSessionValidation | None = None
    try:
        from pathlib import Path
        import json

        mutation_path = Path(rec.skill_dir_path) / "mutation.json"
        if mutation_path.exists():
            mutation_data = json.loads(mutation_path.read_text(encoding="utf-8"))
            cse = mutation_data.get("cross_session_evidence", {})
            if cse:
                cross_session = CrossSessionValidation(
                    similar_sessions_found=cse.get("similar_session_count", 0),
                    recurring_patterns=cse.get("recurring_patterns", []),
                    statistical_confidence_boost=cse.get("confidence_boost", 0.0),
                )
    except Exception:
        # Silently ignore if mutation.json is missing or malformed
        pass

    return CandidateDetailOut(
        **base.model_dump(),
        cross_session_validation=cross_session,
    )


@app.get("/api/candidates/{candidate_id}/diff")
async def get_candidate_diff(candidate_id: str) -> DiffResponse:
    """Get diff between production and candidate versions."""
    rec = get_candidate(candidate_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Candidate not found")

    from pathlib import Path

    diff = compute_diff(
        skill_name=rec.skill_name,
        candidate_dir=Path(rec.skill_dir_path),
    )
    return DiffResponse(**diff)


@app.post("/api/candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: str,
    request: ApproveRequest,
) -> dict[str, Any]:
    """Approve a candidate and publish to production."""
    rec = get_candidate(candidate_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Candidate not found")

    result = approve(candidate_id, approver_id=request.approver_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: str,
    request: RejectRequest,
) -> dict[str, Any]:
    """Reject a candidate and archive it."""
    rec = get_candidate(candidate_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Candidate not found")

    result = reject(
        candidate_id,
        reason=request.reason,
        approver_id=request.approver_id,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/skills/{skill_name}/versions")
async def get_versions(skill_name: str) -> list[CandidateOut]:
    """Get all candidate versions for a skill."""
    records = get_skill_versions(skill_name)
    return [CandidateOut.from_record(r) for r in records]


@app.get("/api/metrics")
async def get_metrics(hours: int = Query(24, ge=1, le=720)) -> dict[str, Any]:
    """Get dashboard metrics summary."""
    db = next(get_storage_session())
    try:
        return get_metric_summary(db, hours=hours)
    finally:
        db.close()


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    """Get candidate statistics."""
    pending = len(list_candidates(status=CandidateStatus.PENDING.value))
    approved = len(list_candidates(status=CandidateStatus.APPROVED.value))
    rejected = len(list_candidates(status=CandidateStatus.REJECTED.value))
    published = len(list_candidates(status=CandidateStatus.PUBLISHED.value))

    return {
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "published": published,
        "total": pending + approved + rejected + published,
    }


def main() -> None:
    """Entry point for `evolver-dashboard` CLI command."""
    uvicorn.run(
        "agent_evolver.dashboard.backend:app",
        host=_config.evolver_dashboard_host,
        port=_config.evolver_dashboard_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
