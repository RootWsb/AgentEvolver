# Agent Evolver 完整指南

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 核心理念](#2-核心理念)
- [3. 系统架构](#3-系统架构)
- [4. 快速开始](#4-快速开始)
- [5. 详细配置](#5-详细配置)
- [6. 模块详解](#6-模块详解)
- [7. 工作流程](#7-工作流程)
- [8. 安全模型](#8-安全模型)
- [9. API 参考](#9-api-参考)
- [10. 测试](#10-测试)
- [11. 高级特性](#11-高级特性)
- [12. 常见问题](#12-常见问题)
- [13. 路线图](#13-路线图)

---

## 1. 项目概述

**Agent Evolver** 是一个旁路(sidecar)进化代理系统，它为已有的 AI Agent 增加"越用越聪明、越来越省 Token"的能力，而无需修改 Agent 本身的任何代码。

**一句话定义**：透明的 OpenAI 兼容 API 代理，它会观察你的 Agent 如何工作，自动学习并提议技能改进，所有改进必须经过人工审批才会生效。

### 1.1 适用场景

- 你的团队维护着一个基于 LLM 的 Agent，拥有多个 skill 文件
- Agent 在实际运行中会出现工具调用失败、重复执行等问题
- 你希望 Agent 能从成功的执行模式中学习新的工作流
- 你**不允许**任何自动修改生产环境的代码

### 1.2 项目来源

本项目是四个开源项目精华的 MVP 拼装：

| 来源项目 | 抽取模块 | 核心贡献 |
|---------|---------|---------|
| **SkillClaw** | Proxy 层 | 透明 API 拦截 + 异步录制 |
| **OpenSpace** | 进化引擎 | FIX/CAPTURED 进化 + 分析器 |
| **Evolver** | 协议层 | Mutation 记录 + 审计日志 + 脱敏 |
| **Hermes** | 存储层 | SQLite 会话存储 + FTS5 检索 |

---

## 2. 核心理念

### 2.1 零侵入接入

你的 Agent 只需要改一个环境变量：

```bash
export OPENAI_BASE_URL=http://127.0.0.1:30000/v1
```

不需要改任何代码，不需要重新部署，Agent 对 Proxy 的存在完全无感知。

### 2.2 只写候选区

**这是整个系统最核心的约束**。

进化引擎产生的所有内容（新 skill、修复后的 skill、派生 skill）永远只写入候选目录(candidate_dir)。生产目录(production_dir)在正常情况下是只读的。

**唯一可以写入生产目录的代码路径**：Dashboard 中的"发布"按钮，它会调用 `publisher.py` 中的 `approve()` 函数，内部使用 `shutil.copy2()` 将候选文件复制到生产目录。

### 2.3 人工审批

每一个进化候选都会出现在 Dashboard 的候选列表中，包含：
- 变更 diff（生产版本 vs 候选版本）
- 置信度评分
- 进化原因说明
- 跨会话验证证据（如有）

只有人工点击"通过并发布"后，变更才会生效。

### 2.4 四道防线

| 防线 | 层级 | 机制 |
|-----|------|------|
| **OS 层** | 操作系统 | 生产目录以只读方式挂载（推荐） |
| **代码层** | 应用代码 | 所有写文件操作通过 `patch.py`，强制重定向到候选区 |
| **路径层** | 路径校验 | `path_guard.py` 校验所有目标路径必须在 `candidate_root/` 下 |
| **审计层** | 日志追溯 | 每次发布追加到 `events.jsonl`，带时间戳和操作用户 |

---

## 3. 系统架构

### 3.1 组件关系图

```
用户浏览器
    │
    ▼ HTTP
┌─────────────────────────────────────────┐
│  Dashboard (React + Vite)               │
│  localhost:30002                        │
└─────────────────────────────────────────┘
    │ API 请求 (/api/*)
    ▼
┌─────────────────────────────────────────┐
│  Dashboard Backend (FastAPI)            │
│  localhost:30001                        │
│                                         │
│  - /api/candidates       (CRUD)         │
│  - /api/candidates/{id}/diff            │
│  - /api/candidates/{id}/approve         │
│  - /api/candidates/{id}/reject          │
│  - /api/metrics          (统计)          │
│  - /api/stats            (计数)          │
└─────────────────────────────────────────┘
    │ 读取 candidate DB + storage DB
    ▼
┌─────────────────────────────────────────┐
│  SQLite 数据库                           │
│                                         │
│  candidates.db ──► 候选记录              │
│  storage.db    ──► 会话/消息/工具调用     │
└─────────────────────────────────────────┘
    ▲
    │ 异步写入 (fire-and-forget)
┌─────────────────────────────────────────┐
│  Proxy (FastAPI)                        │
│  localhost:30000                        │
│                                         │
│  - /v1/chat/completions  (拦截)         │
│  - /v1/models                           │
│  - /healthz                             │
└─────────────────────────────────────────┘
    │ 转发到上游 LLM
    ▼
上游 LLM (OpenAI / Azure / 本地)
```

### 3.2 数据流

**正向流（代理请求）**：
1. Agent 发送 `chat.completions` 请求到 Proxy
2. Proxy 转发到上游 LLM
3. Proxy 异步将请求/响应写入 SQLite（不阻塞响应）
4. 如果 `session_done=true`，触发进化分析

**进化流**：
1. Analyzer 读取会话数据，分析工具调用失败/成功模式
2. 如果发现问题或学习机会，生成 `EvolutionSuggestion`
3. Evolver 应用建议：FIX（修复现有 skill）或 CAPTURED（捕获新 skill）
4. Patch 将结果写入候选目录，同时在 candidate DB 中创建记录
5. Dashboard 显示新候选

**审批流**：
1. 用户在 Dashboard 中查看候选 diff
2. 点击"通过" → `publisher.py` 复制文件到生产目录
3. 写一行审计日志到 `events.jsonl`

---

## 4. 快速开始

### 4.1 环境准备

```bash
# 克隆项目
git clone https://github.com/yourusername/agent-evolver.git
cd agent-evolver

# 创建 Python 虚拟环境
uv venv --python 3.11
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
uv pip install -e ".[dev]"

# 安装前端依赖
cd frontend
npm install
cd ..
```

### 4.2 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# ── 目录配置（最重要） ──
EVOLVER_PRODUCTION_DIR=/path/to/your/agent/skills      # 生产 skill 目录（应只读）
EVOLVER_CANDIDATE_DIR=/path/to/candidate/staging       # 候选区（进化产物写入这里）
EVOLVER_AUDIT_DIR=/path/to/audit                       # 审计日志目录

# ── 上游 LLM ──
EVOLVER_UPSTREAM_BASE_URL=https://api.openai.com/v1
EVOLVER_UPSTREAM_API_KEY=sk-...
EVOLVER_UPSTREAM_MODEL=gpt-4o

# ── 端口 ──
EVOLVER_PROXY_PORT=30000
EVOLVER_DASHBOARD_PORT=30001
```

### 4.3 启动服务

需要**三个终端**同时运行：

**终端 1 — Proxy**：
```bash
evolver-proxy
# 或: python -m agent_evolver.proxy.server
```

**终端 2 — Dashboard 后端**：
```bash
evolver-dashboard
# 或: python -m agent_evolver.dashboard.backend
```

**终端 3 — Dashboard 前端**：
```bash
cd frontend && npm run dev
```

访问 `http://localhost:30002`

### 4.4 接入你的 Agent

```bash
export OPENAI_BASE_URL=http://127.0.0.1:30000/v1
```

Python 示例：

```python
import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:30000/v1",
    api_key="sk-...",  # 会透传给上游 LLM
)

session_id = "task-001"

# 多轮对话中，前面几轮不标记 session_done
client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    extra_headers={
        "x-session-id": session_id,
        "x-session-done": "false",
    },
)

# 最后一轮标记 session_done，触发进化分析
client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    extra_headers={
        "x-session-id": session_id,
        "x-session-done": "true",
    },
)
```

---

## 5. 详细配置

### 5.1 环境变量完整列表

| 变量 | 默认值 | 说明 |
|-----|--------|------|
| `EVOLVER_PRODUCTION_DIR` | *(必填)* | Agent 的生产 skill 目录绝对路径 |
| `EVOLVER_CANDIDATE_DIR` | *(必填)* | 候选区目录绝对路径 |
| `EVOLVER_AUDIT_DIR` | *(必填)* | 审计日志目录绝对路径 |
| `EVOLVER_UPSTREAM_BASE_URL` | *(必填)* | 上游 LLM API 地址 |
| `EVOLVER_UPSTREAM_API_KEY` | *(必填)* | 上游 LLM API 密钥 |
| `EVOLVER_UPSTREAM_MODEL` | `gpt-4o` | 上游模型名称 |
| `EVOLVER_PROXY_HOST` | `127.0.0.1` | Proxy 监听地址 |
| `EVOLVER_PROXY_PORT` | `30000` | Proxy 监听端口 |
| `EVOLVER_DASHBOARD_HOST` | `127.0.0.1` | Dashboard 监听地址 |
| `EVOLVER_DASHBOARD_PORT` | `30001` | Dashboard API 端口 |
| `EVOLVER_STRATEGY` | `balanced` | 进化策略：balanced / innovate / harden / repair-only |
| `EVOLVER_CONFIDENCE_THRESHOLD` | `0.7` | 自动创建候选的置信度阈值 |
| `EVOLVER_LLM_MODEL` | `gpt-4o-mini` | 进化分析使用的 LLM |
| `EVOLVER_STRICT_READONLY` | `false` | 严格模式：生产目录可写时拒绝启动 |
| `EVOLVER_SEMANTIC_MIN_SIMILARITY` | `0.6` | 跨会话相似度阈值 |
| `EVOLVER_SEMANTIC_MAX_SESSIONS` | `20` | 跨会话分析最大会话数 |
| `EVOLVER_PATTERN_MIN_OCCURRENCES` | `3` | 模式识别最小出现次数 |
| `EVOLVER_PATTERN_CONFIDENCE_BOOST_MAX` | `0.2` | 模式置信度最大提升值 |

### 5.2 配置优先级

1. 环境变量（最高优先级）
2. `.env` 文件
3. 默认值（最低优先级）

### 5.3 目录结构约定

```
/path/to/candidate/staging/           # EVOLVER_CANDIDATE_DIR
├── skills/
│   ├── data-fetcher/
│   │   ├── v1/
│   │   │   ├── SKILL.md
│   │   │   ├── mutation.json        # 进化元数据
│   │   │   └── ...
│   │   └── v2/
│   │       └── ...
│   └── email-summarizer/
│       └── v0/
│           └── ...
└── .evolver/
    └── candidates.db                 # 候选记录数据库

/path/to/audit/                       # EVOLVER_AUDIT_DIR
└── events.jsonl                      # 审计日志（追加写）
```

---

## 6. 模块详解

### 6.1 Proxy 层 (`agent_evolver/proxy/`)

#### `server.py`
FastAPI 应用，暴露三个端点：
- `POST /v1/chat/completions` — 核心拦截点
- `GET /v1/models` — 返回上游模型列表
- `GET /healthz` — 健康检查

关键逻辑：
1. 解析请求中的 `x-session-id` 和 `x-session-done` 头
2. 记录请求消息到内存缓冲区
3. 转发到上游 LLM（通过 `httpx.AsyncClient`）
4. 记录响应消息和工具调用
5. 如果 `session_done=true`，关闭会话并触发进化

#### `forwarder.py`
使用 `httpx.AsyncClient` 向上游 LLM 转发请求，支持：
- 连接池复用
- 超时配置
- 错误重试

#### `recorder.py`
`SessionRecorder` 类：
- 内存中维护待持久化的会话缓冲区（最大 100 个）
- 自动清理超过 1 小时的过期会话
- 后台线程写入 SQLite（不阻塞响应）

### 6.2 存储层 (`agent_evolver/storage/`)

#### `models.py`
SQLAlchemy 模型：
- `Session` — 会话记录（id, agent_id, user_id, task_desc, status, total_tokens, started_at, ended_at）
- `Message` — 消息记录（session_id, role, content, tokens, ts）
- `ToolCall` — 工具调用（session_id, tool_name, args, result, status, ts）
- `PatternOccurrence` — 跨会话模式发现记录

#### `session_store.py`
会话 CRUD 操作：创建会话、添加消息、记录工具调用、关闭会话。

#### `queries.py`
查询 API：
- `get_metric_summary()` — Dashboard 指标统计
- `get_failed_tools()` — 获取失败工具列表
- `get_session_conversation()` — 获取会话对话历史
- `get_session_tools()` — 获取会话工具调用

#### `semantic_queries.py` (Scheme 01)
跨会话语义查询：
- `find_similar_sessions()` — 基于任务描述语义相似度查找（FTS5 + LIKE 回退）
- `find_recurring_tool_sequences()` — 检测跨会话的重复工具序列
- `find_message_patterns()` — 消息 n-gram 重叠检测

#### `pattern_store.py` (Scheme 01)
模式统计：
- `compute_pattern_hash()` — 计算模式指纹
- `record_pattern_occurrence()` — 记录模式出现
- `get_pattern_stats()` — 获取模式统计
- `mark_pattern_captured()` — 标记模式已被捕获

### 6.3 进化引擎 (`agent_evolver/engine/`)

#### `analyzer.py`
任务后分析器：
1. 读取会话对话和工具调用
2. 识别失败的工具
3. 推断 skill 应用情况（基于对话文本的启发式匹配）
4. **跨会话语义聚类**（Scheme 01）：查找历史相似会话、检测重复模式
5. 生成进化建议：
   - FIX：工具反复失败时建议修复
   - CAPTURED：任务成功完成但未使用 skill 时建议捕获新工作流

#### `evolver.py`
进化协调器：
1. 调用 Analyzer 获取分析结果
2. 过滤置信度低于阈值的建议
3. 应用建议：
   - FIX → `fix_skill()` — 复制生产 skill 到候选区，应用修复
   - CAPTURED → `create_skill()` — 在候选区创建新 skill
4. 记录审计日志

#### `patch.py`
唯一写文件的模块，三入口：
- `create_skill()` — 创建新 skill（v0）
- `fix_skill()` — 修复现有 skill（创建 vN+1）
- `derive_skill()` — 派生新 skill（合并多个 skill）

所有入口都通过 `path_guard.py` 校验目标路径在候选区内。

#### `candidate_store.py`
候选区 SQLite 管理：
- `CandidateRecord` 模型（id, candidate_id, skill_name, version, status, evolution_type, confidence_score, ...）
- `list_candidates()` — 带过滤的分页查询
- `get_candidate()` — 按 ID 获取
- `get_skill_versions()` — 获取 skill 的所有版本

### 6.4 协议层 (`agent_evolver/protocol/`)

#### `mutation.py`
`Mutation` dataclass → 序列化为 `mutation.json`：
- 记录进化的完整上下文（候选 ID、skill 名、版本、类型、置信度、原因）
- 包含跨会话验证证据（Scheme 01）

#### `audit.py`
审计日志：
- 每条记录是一行 JSON（JSON Lines 格式）
- 包含时间戳、操作用户、候选 ID、变更摘要

#### `sanitize.py`
凭据脱敏：
- 在写入审计日志前，用正则表达式脱敏 API key、密码、token

### 6.5 安全层 (`agent_evolver/security/`)

#### `readonly_guard.py`
启动时检查生产目录是否可写：
- 严格模式（`EVOLVER_STRICT_READONLY=true`）：可写时拒绝启动
- 非严格模式（默认）：可写时打印 WARNING

#### `path_guard.py`
路径校验：
- `assert_candidate_path(path)` — 断言路径在候选区内
- `get_candidate_skill_dir(skill_name, version)` — 安全构建候选目录路径

### 6.6 Dashboard (`agent_evolver/dashboard/`)

#### `backend.py`
FastAPI 路由：
- `GET /api/health` — 健康检查
- `GET /api/candidates` — 候选列表（支持过滤、分页）
- `GET /api/candidates/{id}` — 候选详情（含跨会话验证）
- `GET /api/candidates/{id}/diff` — 候选 vs 生产 diff
- `POST /api/candidates/{id}/approve` — 通过并发布
- `POST /api/candidates/{id}/reject` — 拒绝
- `GET /api/metrics` — 指标统计
- `GET /api/stats` — 状态计数

#### `diff_engine.py`
文本 diff：使用 `difflib.unified_diff` 生成生产文件和候选文件的差异。

#### `publisher.py`
发布逻辑：
- `approve()` — 验证候选状态为 pending/auto_validated，复制文件到生产目录，更新状态为 published
- `reject()` — 验证候选状态，移动到 archive 目录，更新状态为 rejected

### 6.7 前端 (`frontend/`)

React 18 + Vite + Tailwind CSS。

#### 页面
- `CandidateList.tsx` — 候选卡片网格，支持搜索和状态筛选
- `CandidateDetail.tsx` — 候选详情：元数据、置信度条、跨会话验证、变更 diff、通过/拒绝操作
- `MetricsPage.tsx` — 指标统计：会话数、成功率、Token 消耗、候选状态分布

#### 组件
- `CandidateCard.tsx` — 候选卡片（skill 名、版本、状态标签、置信度条、进化原因摘要）
- `DiffViewer.tsx` — 代码 diff 高亮显示
- `Navbar.tsx` — 侧边栏导航
- `StatusPill.tsx` — 状态徽章
- `ThemeToggle.tsx` — 明暗主题切换

---

## 7. 工作流程

### 7.1 日常开发流程

```
1. 启动三服务（Proxy + Dashboard 后端 + Dashboard 前端）
   
2. 将 Agent 的 OPENAI_BASE_URL 指向 Proxy
   
3. Agent 正常运行任务
   
4. Proxy 自动录制会话到 SQLite
   
5. 任务结束时标记 session_done，触发进化分析
   
6. Analyzer 检查是否有失败工具 → FIX 建议
   Analyzer 检查是否成功但未用 skill → CAPTURED 建议
   
7. Evolver 将建议写入候选区 + candidate DB
   
8. Dashboard 显示新候选
   
9. 人工审阅候选的 diff 和原因
   
10. 点击"通过并发布" → 文件复制到生产目录
```

### 7.2 手动创建测试候选

如果希望在没有真实 Agent 流量的情况下测试 Dashboard UI：

```bash
cd agent-evolver
python scripts/seed_candidates.py
```

这会创建 5 条不同状态、不同类型的测试候选数据。

---

## 8. 安全模型

### 8.1 四道防线详解

**第一道：OS 层**
在生产环境中，将生产 skill 目录以只读方式挂载到容器：

```yaml
# docker-compose.yml
volumes:
  - ./production:/data/production:ro
```

这样即使代码有 bug，容器内也无法写入生产目录。

**第二道：代码层**
进化引擎中所有 `open(..., "w")` 和 `shutil.copytree()` 调用都通过 `patch.py`，而 `patch.py` 在写入前会调用 `path_guard.assert_candidate_path(target)`。

**第三道：路径层**
`path_guard.py` 的实现：

```python
def assert_candidate_path(path: Path) -> None:
    resolved = path.resolve()
    candidate_root = Path(_config.evolver_candidate_dir).resolve()
    if not str(resolved).startswith(str(candidate_root)):
        raise PermissionError(f"Path {resolved} is outside candidate root {candidate_root}")
```

任何试图写入候选区之外的路径都会抛出 `PermissionError`。

**第四道：审计层**
每次发布操作追加一行到 `events.jsonl`：

```json
{"ts": "2025-05-09T12:00:00Z", "event": "publish", "candidate_id": "abc123", "skill_name": "data-fetcher", "version": 3, "approver": "dashboard"}
```

可以定期对比生产目录与审计快照，发现异常变更。

### 8.2 凭据脱敏

Proxy 在将消息写入 SQLite 前，会通过 `sanitize.py` 脱敏：
- API keys（`sk-...`、`AK-...` 等格式）
- 密码字段（`password`、`passwd`、`pwd`）
- Token 字段

---

## 9. API 参考

### 9.1 Proxy API（OpenAI 兼容）

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | `/v1/chat/completions` | 转发到上游 LLM，异步录制会话 |
| GET | `/v1/models` | 返回上游模型列表 |
| GET | `/healthz` | 健康检查 |

**请求头**：
- `x-session-id` — 会话 ID（多轮对话中保持一致）
- `x-session-done` — `"true"` 表示这是最后一轮，触发进化分析
- `x-agent-id` — Agent 标识（可选）
- `x-user-id` — 用户标识（可选）

### 9.2 Dashboard API

#### 健康检查
```
GET /api/health
Response: {"status": "ok"}
```

#### 候选列表
```
GET /api/candidates?status=pending&limit=100&offset=0
Response: [
  {
    "candidate_id": "abc123",
    "skill_name": "data-fetcher",
    "version": 3,
    "status": "pending",
    "evolution_type": "fix",
    "confidence_score": 0.92,
    "reason": "修复分页查询问题",
    "created_at": "2025-05-09T12:00:00Z",
    "skill_dir_path": "/path/to/candidate/skills/data-fetcher/v3"
  }
]
```

#### 候选详情
```
GET /api/candidates/{candidate_id}
Response: {
  ...候选列表字段,
  "cross_session_validation": {
    "similar_sessions_found": 5,
    "recurring_patterns": [...],
    "statistical_confidence_boost": 0.15
  }
}
```

#### 候选 Diff
```
GET /api/candidates/{candidate_id}/diff
Response: {
  "skill_name": "data-fetcher",
  "production_dir": "/path/to/production/skills/data-fetcher",
  "candidate_dir": "/path/to/candidate/skills/data-fetcher/v3",
  "files": [...],
  "new_files": [...],
  "removed_files": [...]
}
```

#### 通过候选
```
POST /api/candidates/{candidate_id}/approve
Body: {"approver_id": "dashboard"}
Response: {"success": true, "candidate_id": "abc123"}
```

#### 拒绝候选
```
POST /api/candidates/{candidate_id}/reject
Body: {"reason": "不符合规范", "approver_id": "dashboard"}
Response: {"success": true, "candidate_id": "abc123"}
```

#### 指标统计
```
GET /api/metrics?hours=24
Response: {
  "period_hours": 24,
  "total_sessions": 100,
  "completed_sessions": 95,
  "failed_sessions": 5,
  "total_tokens": 50000
}
```

#### 状态计数
```
GET /api/stats
Response: {
  "pending": 3,
  "approved": 1,
  "rejected": 2,
  "published": 5,
  "total": 11
}
```

---

## 10. 测试

### 10.1 运行测试

```bash
pytest tests/ -v
```

### 10.2 测试覆盖

| 测试文件 | 验证内容 | 关键断言 |
|---------|---------|---------|
| `test_proxy_transparent.py` | Proxy 透明转发 | 响应内容与直接调用上游一致 |
| `test_no_production_write.py` | 生产目录只读 | 进化前后生产目录 checksum 不变 |
| `test_candidate_lifecycle.py` | 候选生命周期 | create → pending → reject → archive |
| `test_publish_flow.py` | 发布流程 | approve → 生产目录更新 + 审计日志 |
| `test_semantic_pattern_mining.py` | 跨会话模式 | 16 个测试覆盖相似会话、重复序列、模式存储、置信度提升 |

### 10.3 已知问题

当前有 6 个预存测试失败，原因是模块级配置缓存导致的测试隔离问题，不影响实际功能。将在后续版本中修复。

---

## 11. 高级特性

### 11.1 跨会话语义模式挖掘 (Scheme 01)

已实现。当 Analyzer 处理一个会话时：

1. 提取任务描述
2. 在历史会话中查找语义相似的任务（FTS5 全文检索 + LIKE 回退）
3. 如果找到足够多的相似会话，检测它们之间的重复工具序列
4. 重复模式越多，CAPTURED 进化的置信度越高

配置项：
- `EVOLVER_SEMANTIC_MIN_SIMILARITY` — 相似度阈值
- `EVOLVER_SEMANTIC_MAX_SESSIONS` — 最大分析会话数
- `EVOLVER_PATTERN_MIN_OCCURRENCES` — 模式最小出现次数
- `EVOLVER_PATTERN_CONFIDENCE_BOOST_MAX` — 置信度最大提升

### 11.2 进化策略

通过 `EVOLVER_STRATEGY` 配置：

| 策略 | 行为 |
|-----|------|
| `balanced` | 默认，FIX 和 CAPTURED 都启用 |
| `innovate` | 优先 CAPTURED，更激进地发现新 skill |
| `harden` | 优先 FIX，专注于修复现有问题 |
| `repair-only` | 只产生 FIX，不产生 CAPTURED |

---

## 12. 常见问题

**Q: Proxy 会拖慢 Agent 的响应速度吗？**
A: 不会。Proxy 使用 `asyncio` 异步转发请求，会话录制是 fire-and-forget 后台任务，不阻塞响应返回给 Agent。

**Q: 如果 Proxy 挂了，Agent 还能工作吗？**
A: 不能。Agent 的 `OPENAI_BASE_URL` 指向了 Proxy，如果 Proxy 不可用，Agent 的 LLM 调用会失败。生产环境建议在前方加负载均衡或健康检查，以便在 Proxy 故障时自动回退到直接调用上游。

**Q: 进化质量不好怎么办？**
A: 调整 `EVOLVER_CONFIDENCE_THRESHOLD` 提高阈值（默认 0.7），或切换 `EVOLVER_STRATEGY` 到 `harden` 减少噪音。Dashboard 的人工审批是最终防线。

**Q: 如何清空测试数据？**
A: 删除 `candidate/skills/` 目录和 `candidate/.evolver/candidates.db`，然后重新启动 Dashboard 后端。

**Q: 支持流式响应 (SSE) 吗？**
A: MVP 阶段暂不支持真正的 SSE 流式透传。Agent 需要使用非流式模式（`stream=false`）。

---

## 13. 路线图

### 已实现 ✅

- [x] 透明 API 代理 + 异步会话录制
- [x] FIX / CAPTURED 进化模式
- [x] 候选区 + 人工审批 Dashboard
- [x] 四道防线安全模型
- [x] 跨会话语义模式挖掘 (Scheme 01)

### 计划中 📝

- [ ] **Shadow A/B Testing (Scheme 02)** — 在候选区并行运行新旧版本对比
- [ ] **GEP Gene Crossover (Scheme 03)** — 遗传进化算法，skill 基因交叉和变异
- [ ] **Version DAG Lineage (Scheme 04)** — 版本有向无环图，可视化进化血缘
- [ ] **Regression Trigger Defense (Scheme 05)** — 自动回归测试，防止进化退化
- [ ] **Multi-Agent Collaborative Evolution (Scheme 06)** — 多 Agent 间的 skill 共享和协同进化
- [ ] **Realtime Evolution (Scheme 07)** — 会话中实时进化建议，不等待 session_done
- [ ] SSE 流式响应透传
- [ ] DERIVED 进化模式（skill 组合/拆分）
- [ ] 工具退化触发器（检测到工具长期不用时建议删除）
- [ ] 指标阈值触发器（Token 消耗异常时触发分析）
- [ ] 自动验证 worker（脱离人工审批的自动发布）
- [ ] 共享存储后端（OSS/S3）
- [ ] 飞书/钉钉通知集成

---

*文档版本: v0.1.0 | 最后更新: 2025-05-09*
