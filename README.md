# Agent Evolver

> **Sidecar Evolution Proxy** — Make your AI agent smarter over time without touching production files.

<p align="center">
  <img src="docs/assets/architecture.png" alt="Architecture" width="700">
</p>

## What is this?

Agent Evolver sits beside your existing AI agent as a transparent OpenAI-compatible API proxy. It observes every conversation, learns from successful patterns, and proposes skill improvements — all of which land in a **staging area** for human review before any production file is ever modified.

**Zero code changes** to your agent. Just point `OPENAI_BASE_URL` at the proxy.

## Key Features

| Feature | Description |
|---------|-------------|
| **Transparent Proxy** | Intercepts OpenAI-compatible API calls, forwards to upstream LLM, records sessions asynchronously |
| **Evolution Engine** | Post-execution analysis produces FIX (repair existing skills) and CAPTURED (learn new workflows) candidates |
| **Cross-Session Pattern Mining** | Discovers recurring tool sequences and semantic patterns across similar sessions to boost confidence |
| **Candidate Staging** | All evolved skills go to a candidate directory — **never** production directly |
| **Human Review Dashboard** | React + Tailwind UI for browsing candidates, viewing diffs, and approving/rejecting changes |
| **Four-Layer Defense** | OS-level readonly + code-level path guard + path validation + audit logging |

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Node.js 18+ (for the dashboard frontend)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agent-evolver.git
cd agent-evolver

# Install Python dependencies
uv venv --python 3.11
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your production skill directory, upstream LLM keys, etc.
```

Key variables:

| Variable | Purpose |
|----------|---------|
| `EVOLVER_PRODUCTION_DIR` | Your agent's production skill directory (read-only guard enforced) |
| `EVOLVER_CANDIDATE_DIR` | Where evolution outputs land (staging area) |
| `EVOLVER_UPSTREAM_BASE_URL` | Real LLM endpoint (e.g. `https://api.openai.com/v1`) |
| `EVOLVER_UPSTREAM_API_KEY` | API key for the upstream LLM |

### Start Services

Three terminals:

```bash
# Terminal 1 — Proxy (intercepts agent LLM calls, triggers evolution)
evolver-proxy

# Terminal 2 — Dashboard backend (API server)
evolver-dashboard

# Terminal 3 — Dashboard frontend (React UI)
cd frontend && npm run dev
```

Then open `http://localhost:30002`.

### Connect Your Agent

```bash
export OPENAI_BASE_URL=http://127.0.0.1:30000/v1
```

Mark the final turn of each task with `x-session-done: true` to trigger post-execution analysis:

```python
import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:30000/v1",
    api_key="sk-...",  # forwarded to upstream
)

# Normal turns: session_done=false
client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    extra_headers={"x-session-id": "task-001", "x-session-done": "false"},
)

# Final turn: triggers evolution analysis
client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    extra_headers={"x-session-id": "task-001", "x-session-done": "true"},
)
```

## Architecture

```
Your Agent ──► Proxy (30000) ──► Upstream LLM
                  │
                  ▼ 异步录制
              SQLite (sessions, messages, tool_calls)
                  │
                  ▼ session_done
              Analyzer (cross-session pattern mining)
                  │
                  ▼ evolution suggestions
              Evolver (FIX / CAPTURED)
                  │
                  ▼ 只写候选区
              Candidate Staging
                  │
                  ▼ 人工审批
              Dashboard (30001/30002)
                  │
                  ▼ 发布（唯一写生产路径）
              Production Skill Directory
```

## Project Structure

```
agent_evolver/
├── proxy/          # FastAPI proxy — intercept + record
├── storage/        # SQLite + SQLAlchemy models + queries
├── engine/         # Analyzer + Evolver + Patch + Candidate Store
├── protocol/       # Mutation JSON + Audit logging + Sanitization
├── security/       # Readonly guard + Path guard
└── dashboard/      # FastAPI backend + React frontend

frontend/           # React 18 + Vite + Tailwind CSS
tests/              # Integration tests
docs/roadmap/       # 7 advanced integration schemes
```

## Roadmap

| # | Scheme | Status |
|---|--------|--------|
| 01 | Semantic Pattern Mining (cross-session) | ✅ Implemented |
| 02 | Shadow A/B Testing | 📝 Planned |
| 03 | GEP Gene Crossover | 📝 Planned |
| 04 | Version DAG Lineage | 📝 Planned |
| 05 | Regression Trigger Defense | 📝 Planned |
| 06 | Multi-Agent Collaborative Evolution | 📝 Planned |
| 07 | Realtime Evolution | 📝 Planned |

See [`docs/roadmap/`](docs/roadmap/) for detailed designs.

## Testing

```bash
pytest tests/ -v
```

Key test coverage:

| Test | What it verifies |
|------|-----------------|
| `test_proxy_transparent.py` | Proxy does not alter upstream responses |
| `test_no_production_write.py` | Engine never writes to production directory |
| `test_candidate_lifecycle.py` | Full candidate create → reject → archive flow |
| `test_publish_flow.py` | Approve → production update + audit log |
| `test_semantic_pattern_mining.py` | Cross-session pattern detection + confidence boost |

## Security Model

| Layer | Mechanism |
|-------|-----------|
| **OS** | Production directory mounted read-only; startup warning if writable |
| **Code** | All disk writes go through `patch.py` — single gatekeeper |
| **Path** | `path_guard.py` validates every target path is under `candidate_root/` |
| **Audit** | Every publish appends to `events.jsonl` with SHA256 chain |

## Contributing

Contributions are welcome. Areas where help is especially appreciated:

- DERIVED mode evolution (combining multiple skills)
- SSE streaming support in the proxy
- Automatic validation workers
- Docker Compose production deployment
- Additional language support

Please open an issue to discuss large changes before submitting a PR.

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center"><i>Evolve safely. Review always.</i></p>
