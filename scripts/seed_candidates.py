"""Seed fake candidates for UI testing."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_evolver.config import get_config
from agent_evolver.engine.candidate_store import (
    init_candidate_db,
    CandidateRecord,
)
from agent_evolver.engine.candidate_store import get_candidate_session
from agent_evolver.engine.types import CandidateStatus

_config = get_config()


SEED_DATA = [
    {
        "skill_name": "data_fetcher",
        "version": 3,
        "status": CandidateStatus.PENDING.value,
        "evolution_type": "fix",
        "confidence_score": 0.92,
        "reason": "修复了在分页查询时重复读取 last_cursor 的问题，避免无限循环。",
    },
    {
        "skill_name": "email_summarizer",
        "version": 1,
        "status": CandidateStatus.AUTO_VALIDATED.value,
        "evolution_type": "captured",
        "confidence_score": 0.78,
        "reason": "从成功会话中捕获了邮件摘要的标准化流程，包含发件人提取和主题归类。",
    },
    {
        "skill_name": "report_generator",
        "version": 5,
        "status": CandidateStatus.APPROVED.value,
        "evolution_type": "fix",
        "confidence_score": 0.85,
        "reason": "优化了图表渲染的内存占用，将大图缓存策略从全量缓存改为 LRU。",
    },
    {
        "skill_name": "slack_notifier",
        "version": 2,
        "status": CandidateStatus.REJECTED.value,
        "evolution_type": "derived",
        "confidence_score": 0.45,
        "reason": "建议合并 webhook 和 bot 两种通知方式，但实现过于侵入，与现有配置冲突。",
    },
    {
        "skill_name": "code_reviewer",
        "version": 4,
        "status": CandidateStatus.PENDING.value,
        "evolution_type": "fix",
        "confidence_score": 0.63,
        "reason": "添加了 Python 类型注解检查步骤，减少运行时类型错误。",
    },
]


def seed():
    init_candidate_db()
    session = next(get_candidate_session())

    candidate_root = Path(_config.evolver_candidate_dir)
    candidate_root.mkdir(parents=True, exist_ok=True)

    existing = session.query(CandidateRecord.candidate_id).all()
    existing_ids = {r[0] for r in existing}

    for item in SEED_DATA:
        candidate_id = f"test_{item['skill_name']}_v{item['version']}"
        if candidate_id in existing_ids:
            print(f"  skip  {candidate_id} (already exists)")
            continue

        skill_dir = candidate_root / item["skill_name"] / f"v{item['version']}"
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write a fake SKILL.md
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            f"# {item['skill_name']}\n\n"
            f"Version: {item['version']}\n\n"
            f"Evolution: {item['evolution_type']}\n\n"
            f"Confidence: {item['confidence_score']}\n\n"
            f"Reason: {item['reason']}\n\n"
            "---\n\n"
            "## Original Content\n\n"
            "This is a test skill for UI verification.\n",
            encoding="utf-8",
        )

        # Write mutation.json with cross-session evidence for some
        mutation = {
            "candidate_id": candidate_id,
            "skill_name": item["skill_name"],
            "version": item["version"],
            "evolution_type": item["evolution_type"],
            "confidence_score": item["confidence_score"],
            "reason": item["reason"],
        }
        if item["confidence_score"] > 0.7:
            mutation["cross_session_evidence"] = {
                "similar_session_count": int(item["confidence_score"] * 10),
                "recurring_patterns": [
                    {"pattern": "tool_sequence_A_B_C", "frequency": 5},
                    {"pattern": "retry_then_fallback", "frequency": 3},
                ],
                "confidence_boost": round((item["confidence_score"] - 0.7) * 0.5, 3),
            }

        import json

        (skill_dir / "mutation.json").write_text(
            json.dumps(mutation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        rec = CandidateRecord(
            candidate_id=candidate_id,
            skill_name=item["skill_name"],
            version=item["version"],
            status=item["status"],
            evolution_type=item["evolution_type"],
            confidence_score=item["confidence_score"],
            mutation_json_path=str(skill_dir / "mutation.json"),
            skill_dir_path=str(skill_dir),
            reason=item["reason"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(rec)
        existing_ids.add(candidate_id)
        print(f"  added {candidate_id}")

    session.commit()
    session.close()
    print(f"\nDone. Check http://localhost:30002")


if __name__ == "__main__":
    seed()
