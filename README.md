# Agent Evolver

> **旁路进化代理系统** — 无需修改生产文件，让你的 AI Agent 越用越聪明。

Agent Evolver 以透明的 OpenAI 兼容 API 代理方式，旁路接入你现有的 AI Agent。它观察每一次对话，从成功模式中自动学习，并提议技能改进 —— 所有改进产物都会进入**候选区**，经人工审批确认后才会生效。

**Agent 端零代码改动**，只需将 `OPENAI_BASE_URL` 指向代理即可。

---

## 核心特性

| 特性 | 说明 |
|-----|------|
| **透明代理** | 拦截 OpenAI 兼容 API 调用，透传上游 LLM，异步录制完整会话 |
| **进化引擎** | 任务后自动分析，产生 FIX（修复现有技能）和 CAPTURED（捕获新工作流）两种候选 |
| **跨会话模式挖掘** | 在历史相似会话中发现重复工具序列和语义模式，提升进化置信度 |
| **候选区机制** | 所有进化产物只写入候选目录，**绝不**直接触碰生产目录 |
| **人工审批面板** | React + Tailwind 仪表盘，浏览候选、查看 Diff、通过/拒绝变更 |
| **四道防线安全模型** | OS 层只读挂载 + 代码层统一写入口 + 路径层强制校验 + 审计层完整日志 |

---

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- Node.js 18+（仪表盘前端）

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/agent-evolver.git
cd agent-evolver

# 安装 Python 依赖
uv venv --python 3.11
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# 安装前端依赖
cd frontend
npm install
cd ..
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的生产目录、上游 LLM 密钥等
```

关键变量：

| 变量 | 用途 |
|-----|------|
| `EVOLVER_PRODUCTION_DIR` | Agent 的生产 skill 目录（受只读保护） |
| `EVOLVER_CANDIDATE_DIR` | 候选区目录（进化产物写入这里） |
| `EVOLVER_UPSTREAM_BASE_URL` | 上游 LLM 端点（如 `https://api.openai.com/v1`） |
| `EVOLVER_UPSTREAM_API_KEY` | 上游 LLM API 密钥 |

### 启动服务

需要**三个终端**同时运行：

```bash
# 终端 1 — 代理（拦截 Agent LLM 调用，触发进化）
evolver-proxy

# 终端 2 — 仪表盘后端（API 服务）
evolver-dashboard

# 终端 3 — 仪表盘前端（React UI）
cd frontend && npm run dev
```

然后访问 `http://localhost:30002`。

### 接入你的 Agent

```bash
export OPENAI_BASE_URL=http://127.0.0.1:30000/v1
```

在每次任务的**最后一轮请求**中标记 `x-session-done: true`，触发任务后进化分析：

```python
import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:30000/v1",
    api_key="sk-...",  # 透传给上游 LLM
)

# 前面几轮：session_done=false
client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    extra_headers={"x-session-id": "task-001", "x-session-done": "false"},
)

# 最后一轮：触发进化分析
client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    extra_headers={"x-session-id": "task-001", "x-session-done": "true"},
)
```

---

## 架构

```
你的 Agent ──► 代理 (30000) ──► 上游 LLM
                  │
                  ▼ 异步录制
              SQLite (sessions, messages, tool_calls)
                  │
                  ▼ session_done
              分析器 (跨会话模式挖掘)
                  │
                  ▼ 进化建议
              进化引擎 (FIX / CAPTURED)
                  │
                  ▼ 只写候选区
              候选区 (Candidate Staging)
                  │
                  ▼ 人工审批
              仪表盘 (30001/30002)
                  │
                  ▼ 发布（唯一写生产路径）
              生产 Skill 目录
```

## 项目结构

```
agent_evolver/
├── proxy/          # FastAPI 代理 — 拦截 + 录制
├── storage/        # SQLite + SQLAlchemy 模型 + 查询
├── engine/         # 分析器 + 进化器 + 补丁 + 候选存储
├── protocol/       # Mutation JSON + 审计日志 + 脱敏
├── security/       # 只读守卫 + 路径守卫
└── dashboard/      # FastAPI 后端 + React 前端

frontend/           # React 18 + Vite + Tailwind CSS
tests/              # 集成测试
docs/               # 文档 + 路线图
```

---

## 路线图

| # | 方案 | 状态 |
|---|------|------|
| 01 | 跨会话语义模式挖掘 | ✅ 已实现 |
| 02 | 影子 A/B 测试 | 📝 计划中 |
| 03 | GEP 基因交叉进化 | 📝 计划中 |
| 04 | 版本 DAG 血缘追踪 | 📝 计划中 |
| 05 | 回归触发防御 | 📝 计划中 |
| 06 | 多 Agent 协同进化 | 📝 计划中 |
| 07 | 实时进化 | 📝 计划中 |

详见 [`docs/roadmap/`](docs/roadmap/)。

---

## 测试

```bash
pytest tests/ -v
```

关键测试覆盖：

| 测试文件 | 验证内容 |
|---------|---------|
| `test_proxy_transparent.py` | 代理透明转发，不破坏上游响应 |
| `test_no_production_write.py` | 进化引擎绝不写入生产目录 |
| `test_candidate_lifecycle.py` | 候选区完整生命周期 |
| `test_publish_flow.py` | 发布流程 + 审计日志 |
| `test_semantic_pattern_mining.py` | 跨会话模式检测 + 置信度提升 |

---

## 安全模型

| 防线 | 层级 | 机制 |
|-----|------|------|
| **OS 层** | 操作系统 | 生产目录以只读方式挂载 |
| **代码层** | 应用代码 | 所有写操作通过 `patch.py`，强制重定向到候选区 |
| **路径层** | 路径校验 | `path_guard.py` 强制校验目标路径在候选区内 |
| **审计层** | 日志追溯 | 每次发布追加 `events.jsonl`，带时间戳和操作用户 |

---

## 完整文档

详见 [`docs/GUIDE.md`](docs/GUIDE.md)，包含：
- 详细配置说明（全部 17 个环境变量）
- 每个模块的源码级解析
- API 参考（含请求/响应示例）
- 常见问题解答

---

## 贡献

欢迎贡献代码。以下领域特别需要帮助：

- DERIVED 模式进化（skill 组合/拆分）
- Proxy SSE 流式响应透传
- 自动验证 Worker
- Docker Compose 生产部署
- 多语言支持

重大变更请先开 Issue 讨论。

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)。

---

<p align="center"><i>安全进化，始终审批。</i></p>
