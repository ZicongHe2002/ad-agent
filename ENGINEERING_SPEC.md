# FirstComment Agent

## Implementation-Ready Engineering Specification

**版本**：v1.0  
**基准日期**：2026-09-02  
**目标读者**：Claude Code / Codex / Cursor / Windsurf，以及负责验收的工程负责人  
**交付形态**：可本地运行的 Modular Monolith + 完整 Mock Platform + 可插拔真实平台 Adapter 骨架

---

## 0. 需求澄清与安全边界

本项目需要解决的真实业务问题是：

1. 评论必须像一个认真读过内容的人写的，而不是统一模板。
2. 账号表达应当稳定、自然、符合真实品牌或已披露运营主体的身份。
3. 评论应具备上下文相关性、语言多样性和平台适配性。
4. 系统应降低垃圾评论、重复评论、虚假体验和过度营销风险。

项目**不实现**：

- 对抗、规避或欺骗平台 AI 检测、内容审核、反垃圾系统。
- 将品牌号、机器号或批量账号伪装为普通真人消费者。
- 生成虚假的购买经历、职业、年龄、性别、生活经历或社会关系。
- 通过错别字注入、随机停顿、设备行为模拟、账号养号、指纹伪造等方式模拟真人。
- 删除、篡改、隐藏或伪造 AI 内容标识、平台来源标识或审计信息。
- 将“AI 检测通过率”设为训练、生成、A/B Test 或上线验收指标。

工程上将把“像真人”落地为：

> **Natural, Specific, Context-Grounded, Truthful and Account-Consistent**

即：自然、具体、基于帖子上下文、真实、不冒充、符合真实账号身份。

---

# 1. Project Overview

## 1.1 项目名称

统一工程名：

```text
FirstComment Agent
```

仓库名：

```text
firstcomment-agent
```

## 1.2 项目目标

系统持续维护一批目标 Creator，在平台能力允许的前提下：

```text
Target Creator
    ↓
Creator Monitor
    ↓
Detect New Post
    ↓
Fetch Content
    ↓
Fast Content Analysis
    ↓
Opportunity Scoring
    ↓
Comment Generation
    ↓
Authenticity & Quality Check
    ↓
Risk Check
    ↓
Official Publish / Human-assisted Publish
    ↓
Analytics
```

系统争取降低从 Creator 发布内容到评论进入发布流程的端到端延迟，并在可测量时统计 Chronological First Comment / Top5。

## 1.3 核心产品原则

```text
Authenticity Before Automation
Quality Before Volume
Capability Before Invocation
Policy Before Publishing
Official API Before Manual
Manual Before Unsupported Automation
Fail Closed
Idempotent
Observable
Simple First
```

## 1.4 首期产品形态

MVP 是一套完整可运行的：

```text
实时内容机会发现
+ AI 评论建议
+ 真实性与质量检查
+ 独立风险检查
+ 人工审核
+ Mock 自动发布
+ 真实平台官方能力适配骨架
+ 延迟与排名分析
```

真实平台如果没有确认的顶级评论发布能力，则进入：

```text
WAITING_MANUAL_PUBLISH
```

而不是调用模拟点击、非公开接口或假 API。

---

# 2. Goals

## G-001 低延迟发现

- 为 Creator 配置优先级和动态 Polling。
- 对 Mock Platform 支持事件驱动。
- 对真实平台仅使用已验证的官方 Webhook、Search API、Polling API 或 Partner Capability。

## G-002 上下文相关评论

- 评论至少锚定帖子中的一个具体元素。
- 不允许只生成“好看”“不错”“支持一下”等无信息评论。
- FAST 模式仍必须具备帖子锚点。

## G-003 非模板化但不伪装

- 通过帖子锚点、真实 Brand Voice、句式库和近期评论去重获得多样性。
- 不通过错别字、随机语病、虚假第一人称经历或人类行为模拟获得“自然感”。

## G-004 真实账号身份

- 每个发布账号必须绑定真实主体类型。
- 品牌账号不得伪装普通消费者。
- 员工或合作方账号需要明确授权和披露策略。

## G-005 安全发布

- 发布前执行 Capability Check、Identity Check、Quality Check、Risk Check、Dedup Check。
- 任何关键检查失败均不得自动发布。

## G-006 可测试

- Mock Platform 完整支持 Creator、Post、Comment、排名、延迟、错误和限流。
- 所有关键流程具备 Unit、Integration 和 E2E 测试。

## G-007 可观测

- 从第一天记录 Detection、Fetch、Analysis、Generation、Quality、Risk、Review、Publish 和 E2E 延迟。
- 对不可测的真实平台排名显示 `UNKNOWN`。

---

# 3. Non-Goals

详见仓库根目录 `NON_GOALS.md`。

MVP 明确不做：

```text
AI detector evasion
AI watermark / label removal
Human persona simulation
Fake consumer identity
Fake purchase or usage experience
Captcha bypass
Device fingerprint spoofing
Anti-bot or anti-crawl bypass
Account farming
Bulk account registration
Browser / emulator auto-click publishing
Ban evasion
Fake likes / follows / replies
Competitor comment-section poaching
Unverified private APIs
```

---

# 4. User Stories

## US-001 Brand Manager

作为 Brand Manager，我可以创建品牌、产品、Campaign、品牌口吻和禁止声明，并知道每条评论引用了哪些品牌事实。

## US-002 Operator

作为运营人员，我可以添加 Creator、查看新内容、选择候选评论、编辑并发布，或者跳过风险内容。

## US-003 Reviewer

作为审核人员，我可以看到帖子摘要、具体锚点、账号身份、候选评论、重复度、真实性风险、商业风险和平台能力。

## US-004 Admin

作为管理员，我可以查看平台能力状态、Token 状态、队列、Worker、失败任务和全局 Kill Switch。

## US-005 Engineer

作为工程师，我可以只启动 Mock Platform 就跑通完整链路，而不依赖任何真实平台权限。

## US-006 Compliance Reviewer

作为合规审核人，我可以追踪评论是 Human Authored、AI Assisted 还是 AI Generated，查看人工修改记录、审批人和平台披露状态。

---

# 5. Functional Requirements

## 5.1 Creator 与监控

| ID | Requirement |
|---|---|
| FR-001 | 创建、更新、停用 Creator |
| FR-002 | 一个 Creator 可绑定多个平台账号 |
| FR-003 | 配置 Creator Priority、Poll Interval 和预期发布时间窗口 |
| FR-004 | 记录 last_checked_at、last_post_at、last_external_post_id |
| FR-005 | 平台不支持监控时明确返回 `UNSUPPORTED` 或 `UNKNOWN` |

## 5.2 内容发现与处理

| ID | Requirement |
|---|---|
| FR-010 | 新 Post 以 `(platform, external_post_id)` 去重 |
| FR-011 | 保存原始 Payload Hash 和规范化内容 |
| FR-012 | 支持 FAST / MEDIUM / SLOW 三条分析路径 |
| FR-013 | 为每条 Post 提取 1–5 个 Concrete Anchors |
| FR-014 | 计算 Opportunity Score 和可解释分项 |

## 5.3 评论生成

| ID | Requirement |
|---|---|
| FR-020 | 使用 Structured Output 返回候选评论 |
| FR-021 | 每条候选包含至少一个帖子锚点 |
| FR-022 | 禁止虚假第一人称体验和虚构身份 |
| FR-023 | 候选评论不得引用未批准的 Product Claim |
| FR-024 | 默认一次模型调用返回 2 条候选；人工审核模式可返回 3 条 |
| FR-025 | Prompt 文件化并记录 prompt_version |

## 5.4 真实性与质量

| ID | Requirement |
|---|---|
| FR-030 | 每个 Brand Account 绑定 Account Identity Profile |
| FR-031 | 每个账号绑定 Brand Voice，不创建虚假“真人 Persona” |
| FR-032 | 计算 relevance、specificity、fluency、voice_match、novelty |
| FR-033 | 与近期评论执行 exact、normalized、n-gram 相似度检查 |
| FR-034 | 检测 generic praise、fake experience、fake identity、unsupported claim |
| FR-035 | 禁止保存或优化 `ai_detector_score` |
| FR-036 | 保存 Content Provenance 和 AI Disclosure Status |

## 5.5 风控与发布

| ID | Requirement |
|---|---|
| FR-040 | RuleRiskEngine 先于 LLMRiskAgent 执行 |
| FR-041 | GENERAL_CREATOR + 品牌提及默认进入 REVIEW |
| FR-042 | COMPETITOR 默认 BLOCK / SKIP |
| FR-043 | Capability 不支持时进入 MANUAL 或 UNSUPPORTED |
| FR-044 | 发布任务必须具备 idempotency_key |
| FR-045 | 发布超时进入 `PUBLISH_UNCERTAIN`，先 Reconcile 再重试 |
| FR-046 | 每个平台、账号、Campaign 支持 Kill Switch |

## 5.6 Analytics

| ID | Requirement |
|---|---|
| FR-050 | Mock Platform 计算 chronological_rank |
| FR-051 | 真实平台不可测时记录 `UNKNOWN` |
| FR-052 | 记录 Human Acceptance Rate 和 Edit Rate |
| FR-053 | 记录 Comment Removal / Rejection 结果（能力允许时） |
| FR-054 | 不使用 AI Detector Pass Rate 作为指标 |

---

# 6. Non-Functional Requirements

## 6.1 Latency Targets

以下是系统目标，不是平台承诺。

| Stage | FAST P50 | FAST P95 |
|---|---:|---:|
| Detection | 2s | 10s |
| Fetch | 300ms | 1.5s |
| Fast Analysis | 150ms | 600ms |
| Generation | 500ms | 1.8s |
| Quality + Rule Risk | 80ms | 300ms |
| LLM Risk（需要时） | 400ms | 1.5s |
| Official Publish | 700ms | 3s |
| AI Ready E2E | 4s | 15s |

Human-assisted 路径：

| Stage | P50 | P95 |
|---|---:|---:|
| Review Queue Wait | 10s | 60s |
| Human Decision | 10s | 60s |
| Manual Publish | 10s | 90s |

## 6.2 Reliability

- 核心 DB 写入成功后才 ACK Queue。
- 关键任务至少一次投递，业务层通过幂等实现 effectively-once。
- Worker 重启不得导致重复评论。
- 单个平台故障不得阻塞其他平台。

## 6.3 Security

- Token 加密保存。
- Secret 不进入日志、数据库明文、前端 Bundle 或 Git。
- RBAC 和审计日志从 MVP 开始实现。

## 6.4 Policy Safety

- Policy Version 过期时关闭 Auto Publish。
- Capability 未验证时不能标记为 `SUPPORTED`。
- AI 内容来源和披露状态必须保留内部记录。

## 6.5 Maintainability

- Python 类型检查通过。
- 核心模块覆盖率目标 ≥ 80%。
- Adapter 契约测试覆盖所有 Capability 状态。

---

# 7. Architecture

## 7.1 架构风格

```text
Modular Monolith
+ Multiple Worker Processes
+ PostgreSQL Source of Truth
+ Redis Broker / Cache / Schedule
+ Adapter-based External Integrations
```

不在 MVP 引入 Kubernetes、Kafka、Service Mesh 或多仓库微服务。

## 7.2 Architecture Diagram

```mermaid
flowchart TD
    UI[Next.js Dashboard] --> API[FastAPI API]

    API --> PG[(PostgreSQL)]
    API --> REDIS[(Redis)]
    API --> SSE[SSE Event Stream]

    SCHED[Polling Scheduler] --> REDIS
    REDIS --> MON[Monitor Workers]
    REDIS --> PIPE[Pipeline Workers]
    REDIS --> PUB[Publish Workers]

    MON --> CAP[Capability Registry]
    MON --> ADAPTERS[Platform Adapters]
    ADAPTERS --> MOCK[Mock Platform]
    ADAPTERS --> OFFICIAL[Verified Official APIs]

    MON --> PG
    PG --> OUTBOX[Outbox Relay]
    OUTBOX --> REDIS

    PIPE --> FETCH[Content Fetcher]
    FETCH --> ANCHOR[Post Anchor Extractor]
    ANCHOR --> OPP[Opportunity Agent]
    OPP --> GEN[Comment Generator]
    GEN --> QUALITY[Authenticity & Quality Evaluator]
    QUALITY --> RISK[Risk Engine]
    RISK --> REVIEW[Human Review]
    RISK --> ROUTER[Publish Router]
    REVIEW --> ROUTER

    ROUTER --> PUB
    PUB --> ADAPTERS
    PUB --> MANUAL[Manual Publish Workflow]

    API --> METRICS[Metrics & Audit]
    MON --> METRICS
    PIPE --> METRICS
    PUB --> METRICS
```

## 7.3 Agent Flow

```mermaid
flowchart LR
    POST[Normalized Post] --> EXTRACT[Extract Concrete Anchors]
    EXTRACT --> SCORE[Opportunity Score]
    SCORE -->|Low| SKIP[Skip]
    SCORE -->|Candidate| STRAT[Select Strategy]
    STRAT --> GEN[Generate 2 Candidates]
    GEN --> Q1[Context Relevance]
    Q1 --> Q2[Truthfulness / Identity]
    Q2 --> Q3[Duplicate / Novelty]
    Q3 --> Q4[Brand Voice]
    Q4 --> RISK[Risk Engine]
    RISK -->|ALLOW| READY[Ready]
    RISK -->|REVIEW| HUMAN[Human Review]
    RISK -->|BLOCK| BLOCK[Blocked]
```

## 7.4 Event Flow

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant M as Monitor Worker
    participant A as Platform Adapter
    participant D as PostgreSQL
    participant O as Outbox Relay
    participant P as Pipeline Worker
    participant R as Risk Engine
    participant U as Publish Router

    S->>M: poll_creator(creator_id)
    M->>A: get_latest_posts()
    A-->>M: post list
    M->>D: insert post + outbox event (transaction)
    D-->>M: committed
    O->>D: load unpublished outbox
    O->>P: post.detected
    P->>D: analyze + candidate + quality
    P->>R: evaluate candidate
    R-->>P: ALLOW / REVIEW / BLOCK
    P->>D: persist decision
    P->>U: publish job if allowed
    U->>A: publish / reply / manual route
    A-->>U: receipt / unsupported
    U->>D: persist result
```

---

# 8. Repository Structure

```text
firstcomment-agent/
├── README.md
├── ENGINEERING_SPEC.md
├── IMPLEMENTATION_ORDER.md
├── NON_GOALS.md
├── PLATFORM_CAPABILITIES.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── platform-adapters.md
│   ├── agents.md
│   ├── api.md
│   ├── development.md
│   ├── deployment.md
│   ├── security.md
│   └── platform-capabilities.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── api/
│       │   ├── deps.py
│       │   ├── error_handlers.py
│       │   └── v1/
│       │       ├── router.py
│       │       ├── auth.py
│       │       ├── brands.py
│       │       ├── products.py
│       │       ├── campaigns.py
│       │       ├── creators.py
│       │       ├── platform_accounts.py
│       │       ├── posts.py
│       │       ├── comments.py
│       │       ├── review.py
│       │       ├── metrics.py
│       │       ├── system.py
│       │       ├── events.py
│       │       └── mock.py
│       ├── core/
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── security.py
│       │   ├── encryption.py
│       │   ├── clock.py
│       │   ├── ids.py
│       │   └── exceptions.py
│       ├── db/
│       │   ├── base.py
│       │   ├── session.py
│       │   └── naming.py
│       ├── domain/
│       │   ├── enums.py
│       │   ├── capabilities.py
│       │   ├── events.py
│       │   ├── state_machine.py
│       │   ├── scoring.py
│       │   └── value_objects.py
│       ├── models/
│       │   ├── user.py
│       │   ├── brand.py
│       │   ├── product.py
│       │   ├── campaign.py
│       │   ├── account.py
│       │   ├── identity_profile.py
│       │   ├── voice_profile.py
│       │   ├── creator.py
│       │   ├── post.py
│       │   ├── comment.py
│       │   ├── risk.py
│       │   ├── publish.py
│       │   ├── event.py
│       │   ├── metric.py
│       │   └── audit.py
│       ├── schemas/
│       │   ├── common.py
│       │   ├── brand.py
│       │   ├── product.py
│       │   ├── campaign.py
│       │   ├── creator.py
│       │   ├── post.py
│       │   ├── comment.py
│       │   ├── review.py
│       │   ├── platform.py
│       │   ├── metric.py
│       │   └── mock.py
│       ├── repositories/
│       │   ├── base.py
│       │   ├── brands.py
│       │   ├── creators.py
│       │   ├── posts.py
│       │   ├── comments.py
│       │   ├── publish_jobs.py
│       │   ├── outbox.py
│       │   └── metrics.py
│       ├── services/
│       │   ├── creator_service.py
│       │   ├── monitor_service.py
│       │   ├── content_service.py
│       │   ├── opportunity_service.py
│       │   ├── comment_service.py
│       │   ├── quality_service.py
│       │   ├── risk_service.py
│       │   ├── review_service.py
│       │   ├── publish_service.py
│       │   ├── metrics_service.py
│       │   └── audit_service.py
│       ├── agents/
│       │   ├── provider.py
│       │   ├── structured_output.py
│       │   ├── anchor_extractor.py
│       │   ├── opportunity_agent.py
│       │   ├── comment_agent.py
│       │   ├── quality_evaluator.py
│       │   └── risk_agent.py
│       ├── prompts/
│       │   ├── manifest.yaml
│       │   ├── anchor_extract_v1.md
│       │   ├── opportunity_score_v1.md
│       │   ├── comment_fast_v1.md
│       │   ├── comment_normal_v1.md
│       │   ├── comment_partner_v1.md
│       │   ├── comment_quality_v1.md
│       │   └── risk_check_v1.md
│       ├── platforms/
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── errors.py
│       │   ├── mock/
│       │   │   ├── adapter.py
│       │   │   ├── service.py
│       │   │   ├── ranking.py
│       │   │   └── failure_injection.py
│       │   ├── douyin/
│       │   │   ├── adapter.py
│       │   │   ├── client.py
│       │   │   └── CAPABILITIES.md
│       │   ├── xiaohongshu/
│       │   │   ├── adapter.py
│       │   │   └── CAPABILITIES.md
│       │   └── wechat_channels/
│       │       ├── adapter.py
│       │       └── CAPABILITIES.md
│       ├── workers/
│       │   ├── broker.py
│       │   ├── middleware.py
│       │   ├── scheduler.py
│       │   ├── monitor_actors.py
│       │   ├── pipeline_actors.py
│       │   ├── publish_actors.py
│       │   ├── outbox_relay.py
│       │   └── health.py
│       ├── observability/
│       │   ├── metrics.py
│       │   ├── tracing.py
│       │   └── timeline.py
│       └── tests/
│           ├── conftest.py
│           ├── unit/
│           ├── integration/
│           ├── contract/
│           └── e2e/
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── dashboard/page.tsx
│   │   ├── creators/page.tsx
│   │   ├── live/page.tsx
│   │   ├── posts/page.tsx
│   │   ├── review/page.tsx
│   │   ├── comments/page.tsx
│   │   ├── campaigns/page.tsx
│   │   ├── brand/page.tsx
│   │   ├── accounts/page.tsx
│   │   ├── risk/page.tsx
│   │   ├── analytics/page.tsx
│   │   └── settings/page.tsx
│   ├── components/
│   ├── lib/
│   └── tests/
└── scripts/
    ├── seed_demo.py
    ├── create_admin.py
    ├── run_e2e_demo.py
    └── verify_capabilities.py
```

## 8.1 目录责任

- `domain/`：枚举、能力模型、状态机、评分公式，无网络与数据库副作用。
- `models/`：SQLAlchemy ORM。
- `schemas/`：API 与 Agent Structured Output 的 Pydantic 模型。
- `services/`：业务编排和事务边界。
- `agents/`：模型 Provider、Prompt、结构化输出和质量评估。
- `platforms/`：平台能力与外部调用。
- `workers/`：Dramatiq Actor、Scheduler、Outbox Relay。
- `observability/`：日志、Metrics、Timeline。
- `tests/contract/`：Adapter 和 Agent Provider 契约测试。

---

# 9. Technology Stack

## 9.1 Backend

```text
Python 3.12+
FastAPI
Pydantic v2
SQLAlchemy 2.x async
Alembic
httpx
```

## 9.2 Worker

选择：

```text
Dramatiq + Redis Broker + AsyncIO Middleware
```

原因：

- 相比自建 Queue，具备成熟的 Actor、Retry 和 Middleware 机制。
- 相比完整 Celery，MVP 配置更少。
- 支持 `async def` Actor，适合平台 API 和 LLM 等 I/O 密集任务。
- ARQ 当前仅维护模式，因此不作为新项目默认依赖。

## 9.3 Storage

```text
PostgreSQL 16+
Redis 7+
S3-compatible Object Storage（MVP 可用本地 MinIO）
```

MVP 不引入独立向量数据库；评论去重使用 PostgreSQL + 规则，后续再加 pgvector。

## 9.4 Frontend

```text
Next.js
TypeScript
React
Tailwind CSS
```

## 9.5 Realtime UI

选择：

```text
Server-Sent Events (SSE)
```

理由：Live Timeline 主要是服务器单向推送，SSE 比 WebSocket 更简单；审核操作仍使用普通 REST。

## 9.6 Testing

```text
pytest
pytest-asyncio
pytest-cov
httpx AsyncClient
testcontainers-python
Playwright
```

## 9.7 Quality Tooling

```text
Ruff
mypy
pre-commit
ESLint
TypeScript strict mode
```

## 9.8 Deployment

```text
Docker
Docker Compose
```

---

# 10. Domain Model

## 10.1 Core Enums

```python
class Platform(str, Enum):
    MOCK = "MOCK"
    XIAOHONGSHU = "XIAOHONGSHU"
    DOUYIN = "DOUYIN"
    WECHAT_CHANNELS = "WECHAT_CHANNELS"

class CapabilityStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    MANUAL = "MANUAL"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    RATE_LIMITED = "RATE_LIMITED"
    DISABLED = "DISABLED"

class CreatorRelationship(str, Enum):
    OWN_ACCOUNT = "OWN_ACCOUNT"
    PARTNER_CREATOR = "PARTNER_CREATOR"
    OFFICIAL_CAMPAIGN_CREATOR = "OFFICIAL_CAMPAIGN_CREATOR"
    GENERAL_CREATOR = "GENERAL_CREATOR"
    BRAND_ACCOUNT = "BRAND_ACCOUNT"
    COMPETITOR = "COMPETITOR"
    BLOCKED_CREATOR = "BLOCKED_CREATOR"

class AccountKind(str, Enum):
    BRAND_OFFICIAL = "BRAND_OFFICIAL"
    EMPLOYEE_DISCLOSED = "EMPLOYEE_DISCLOSED"
    PARTNER_CREATOR = "PARTNER_CREATOR"
    HUMAN_OPERATOR = "HUMAN_OPERATOR"

class ContentProvenance(str, Enum):
    HUMAN_AUTHORED = "HUMAN_AUTHORED"
    AI_ASSISTED_HUMAN_EDITED = "AI_ASSISTED_HUMAN_EDITED"
    AI_GENERATED_HUMAN_APPROVED = "AI_GENERATED_HUMAN_APPROVED"
    AI_GENERATED_AUTO_APPROVED = "AI_GENERATED_AUTO_APPROVED"

class DisclosureStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED_PENDING = "REQUIRED_PENDING"
    DECLARED = "DECLARED"
    PLATFORM_APPLIED = "PLATFORM_APPLIED"
    UNKNOWN = "UNKNOWN"

class CommentStrategy(str, Enum):
    NORMAL_INTERACTION = "NORMAL_INTERACTION"
    EXPERT_COMMENT = "EXPERT_COMMENT"
    LIGHT_BRAND_MENTION = "LIGHT_BRAND_MENTION"
    PARTNER_BRAND_COMMENT = "PARTNER_BRAND_COMMENT"
    PRODUCT_RELATED = "PRODUCT_RELATED"
    CAMPAIGN_DISCLOSURE = "CAMPAIGN_DISCLOSURE"
    SKIP = "SKIP"

class RunMode(str, Enum):
    NORMAL = "NORMAL"
    FAST = "FAST"
    FIRST_COMMENT = "FIRST_COMMENT"
    TOP5_COMMENT = "TOP5_COMMENT"

class RiskDecision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
```

## 10.2 Job States

```python
class CommentJobState(str, Enum):
    DISCOVERED = "DISCOVERED"
    FETCHING = "FETCHING"
    ANALYZING = "ANALYZING"
    SKIPPED = "SKIPPED"
    GENERATING = "GENERATING"
    QUALITY_CHECKING = "QUALITY_CHECKING"
    RISK_CHECKING = "RISK_CHECKING"
    WAITING_REVIEW = "WAITING_REVIEW"
    READY = "READY"
    WAITING_MANUAL_PUBLISH = "WAITING_MANUAL_PUBLISH"
    PUBLISHING = "PUBLISHING"
    PUBLISH_UNCERTAIN = "PUBLISH_UNCERTAIN"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
```

## 10.3 Main Entities

### Brand

```text
id UUID PK
name varchar(120) not null
description text null
default_language varchar(16) default 'zh-CN'
status enum ACTIVE/PAUSED
created_at timestamptz
updated_at timestamptz
```

### Product

```text
id UUID PK
brand_id UUID FK not null
name varchar(160)
category varchar(100)
material text null
price_min numeric null
price_max numeric null
approved_claims jsonb default []
forbidden_claims jsonb default []
active bool default true
```

### Campaign

```text
id UUID PK
brand_id UUID FK
name varchar(160)
run_mode RunMode
start_at timestamptz
end_at timestamptz
allowed_strategies jsonb
creator_relationship_allowlist jsonb
max_comments_per_day int
max_comments_per_creator_per_day int
human_review_required bool
status enum DRAFT/ACTIVE/PAUSED/ENDED
```

### BrandAccount

```text
id UUID PK
brand_id UUID FK
platform Platform
external_account_id varchar(255)
display_name varchar(160)
account_kind AccountKind
identity_profile_id UUID FK
voice_profile_id UUID FK
auto_publish_enabled bool default false
publisher_kill_switch bool default false
auth_status enum
credentials_ciphertext bytea null
credentials_version int
last_auth_verified_at timestamptz null
unique(platform, external_account_id)
```

### AccountIdentityProfile

```text
id UUID PK
legal_or_operating_entity varchar(255)
account_kind AccountKind
public_identity_text text
may_speak_as_consumer bool default false
may_use_first_person_experience bool default false
requires_brand_disclosure bool default true
requires_ai_disclosure_policy_check bool default true
approved_by_user_id UUID null
approved_at timestamptz null
```

规则：

- `BRAND_OFFICIAL.may_speak_as_consumer` 必须为 false。
- `may_use_first_person_experience=true` 只允许有可审计真人作者、真实经历和人工确认。
- 自动路径不得生成第一人称购买/使用体验。

### VoiceProfile

```text
id UUID PK
brand_id UUID FK
name varchar(100)
tone_attributes jsonb
preferred_sentence_length varchar(30)
emoji_policy jsonb
allowed_phrases jsonb
forbidden_phrases jsonb
approved_examples jsonb
version int
active bool
```

VoiceProfile 是品牌表达规范，不是虚假人设。

### Creator

```text
id UUID PK
name varchar(160)
category varchar(100)
relationship_type CreatorRelationship
priority smallint default 50
normal_poll_interval_sec int default 600
warm_poll_interval_sec int default 60
hot_poll_interval_sec int default 10
expected_publish_windows jsonb default []
last_checked_at timestamptz null
last_post_at timestamptz null
monitor_state enum ACTIVE/PAUSED/ERROR
```

### CreatorPlatformAccount

```text
id UUID PK
creator_id UUID FK
platform Platform
external_creator_id varchar(255)
creator_url text null
authorization_id UUID null
last_external_post_id varchar(255) null
metadata jsonb
unique(platform, external_creator_id)
```

### Post

```text
id UUID PK
platform Platform
external_post_id varchar(255)
creator_id UUID FK
published_at timestamptz
detected_at timestamptz
content_updated_at timestamptz null
status enum ACTIVE/DELETED/UNKNOWN
raw_payload_hash varchar(64)
source_capability_snapshot_id UUID
unique(platform, external_post_id)
index(creator_id, published_at desc)
```

### PostContent

```text
post_id UUID PK/FK
title text null
caption text null
hashtags jsonb
mentions jsonb
ocr_text text null
transcript text null
visual_summary text null
content_language varchar(16)
content_hash varchar(64)
data_completeness numeric(4,3)
model_derived_fields jsonb
```

### PostAnchor

```text
id UUID PK
post_id UUID FK
anchor_type enum OBJECT/COLOR/STYLE/TOPIC/QUOTE/ACTION/CLAIM
anchor_text text
source_field varchar(50)
confidence numeric(4,3)
unique(post_id, anchor_type, anchor_text)
```

### OpportunityEvaluation

```text
id UUID PK
post_id UUID FK
campaign_id UUID FK
creator_value numeric
relevance numeric
audience_match numeric
traffic_potential numeric
post_velocity numeric
brand_fit numeric
commercial_risk numeric
platform_risk numeric
final_score numeric
reason_codes jsonb
prompt_version varchar(50)
created_at timestamptz
unique(post_id, campaign_id)
```

### CommentCandidate

```text
id UUID PK
post_id UUID FK
campaign_id UUID FK
brand_account_id UUID FK
strategy CommentStrategy
text text
normalized_text text
content_provenance ContentProvenance
prompt_version varchar(50)
model_provider varchar(50)
model_name varchar(100)
model_request_id varchar(255) null
relevance_score numeric
commercial_score numeric
confidence numeric
referenced_anchor_ids jsonb
referenced_claim_ids jsonb
generation_reason text
status enum GENERATED/SELECTED/REJECTED/BLOCKED
created_at timestamptz
```

### CommentQualityEvaluation

```text
id UUID PK
candidate_id UUID FK unique
anchor_coverage numeric
specificity numeric
fluency numeric
voice_match numeric
novelty numeric
truthfulness numeric
identity_consistency numeric
duplicate_similarity_max numeric
generic_praise_detected bool
fake_experience_detected bool
fake_identity_detected bool
unsupported_claim_detected bool
random_typo_pattern_detected bool
quality_score numeric
decision ALLOW/REVIEW/BLOCK
reasons jsonb
```

注意：Schema 中**不得存在** `ai_detector_score`、`human_probability`、`bot_evasion_score`。

### RiskEvent

```text
id UUID PK
candidate_id UUID FK
rule_decision RiskDecision
llm_decision RiskDecision null
final_decision RiskDecision
risk_score numeric
matched_rules jsonb
reasons jsonb
policy_versions jsonb
created_at timestamptz
```

### ReviewJob

```text
id UUID PK
candidate_id UUID FK
status PENDING/APPROVED/EDITED_APPROVED/REJECTED/EXPIRED
assigned_to UUID null
submitted_at timestamptz
resolved_at timestamptz null
final_text text null
review_notes text null
```

### PublishJob

```text
id UUID PK
candidate_id UUID FK
brand_account_id UUID FK
platform Platform
mode OFFICIAL_API/OFFICIAL_PARTNER/MANUAL/UNSUPPORTED
idempotency_key varchar(255) unique
state CommentJobState
attempt_count int default 0
next_retry_at timestamptz null
started_at timestamptz null
finished_at timestamptz null
external_request_id varchar(255) null
last_error_code varchar(100) null
last_error_message text null
```

### PublishedComment

```text
id UUID PK
publish_job_id UUID FK unique
post_id UUID FK
brand_account_id UUID FK
external_comment_id varchar(255) null
final_text text
content_provenance ContentProvenance
disclosure_status DisclosureStatus
published_at timestamptz
chronological_rank int null
chronological_rank_confidence enum EXACT/ESTIMATED/PARTIAL/UNKNOWN
visible_rank int null
visible_rank_confidence enum EXACT/ESTIMATED/PARTIAL/UNKNOWN
unique(platform, external_comment_id) where external_comment_id is not null
```

---

# 11. Database Schema

## 11.1 关键 Unique Constraints

```sql
UNIQUE (platform, external_post_id)
UNIQUE (platform, external_creator_id)
UNIQUE (platform, external_account_id)
UNIQUE (post_id, campaign_id)
UNIQUE (idempotency_key)
UNIQUE (publish_job_id)
```

## 11.2 Publish Idempotency Key

```text
sha256(
  tenant_id
  + platform
  + brand_account_id
  + external_post_id
  + campaign_id
  + intent_key
)
```

其中 `intent_key` MVP 固定为：

```text
TOP_LEVEL_PRIMARY
```

同一账号对同一 Post、同一 Campaign 默认只允许一条顶级评论。

## 11.3 Outbox Table

```text
outbox_events
- id UUID PK
- aggregate_type varchar
- aggregate_id UUID
- event_type varchar
- event_version int
- payload jsonb
- trace_id UUID
- created_at timestamptz
- published_at timestamptz null
- attempts int default 0
- last_error text null
```

创建 Post 和 `post.detected` Outbox Event 必须在一个数据库事务中完成。

## 11.4 Audit Log

```text
audit_logs
- id UUID PK
- actor_type USER/SYSTEM/WORKER
- actor_id UUID null
- action varchar
- resource_type varchar
- resource_id UUID null
- before jsonb null
- after jsonb null
- trace_id UUID
- created_at timestamptz
```

审计以下操作：

- Brand Voice 修改
- Identity Profile 修改
- Campaign 激活/暂停
- Capability 状态修改
- Auto Publish 开关
- Review 决策
- Comment 编辑
- Publish 请求与结果
- AI Disclosure 状态修改

## 11.5 Migration Rules

- 所有 Migration 可向前执行和在测试环境回滚。
- 禁止在同一个 Migration 中无保护地删除生产列。
- Enum 变更单独 Migration。
- CI 每次执行空库升级到 head。

---

# 12. Platform Adapter

## 12.1 Capability Model

```python
class PlatformCapabilities(BaseModel):
    creator_monitoring: CapabilityStatus
    new_post_webhook: CapabilityStatus
    latest_posts: CapabilityStatus
    post_fetch: CapabilityStatus
    comment_read: CapabilityStatus
    top_level_comment: CapabilityStatus
    comment_reply: CapabilityStatus
    comment_delete: CapabilityStatus
    comment_created_at: CapabilityStatus
    chronological_rank: CapabilityStatus
    visible_rank: CapabilityStatus
    ai_disclosure: CapabilityStatus
```

## 12.2 Adapter Contract

```python
class PlatformAdapter(ABC):
    platform: Platform

    @abstractmethod
    async def get_capabilities(self) -> PlatformCapabilities: ...

    @abstractmethod
    async def get_latest_posts(
        self,
        creator: CreatorPlatformAccount,
        cursor: str | None = None,
    ) -> PostPage: ...

    @abstractmethod
    async def get_post(self, external_post_id: str) -> PlatformPost: ...

    @abstractmethod
    async def get_comments(
        self,
        external_post_id: str,
        cursor: str | None = None,
    ) -> CommentPage: ...

    @abstractmethod
    async def publish_top_level_comment(
        self,
        request: PublishCommentRequest,
    ) -> PublishReceipt: ...

    @abstractmethod
    async def reply_comment(
        self,
        request: ReplyCommentRequest,
    ) -> PublishReceipt: ...

    @abstractmethod
    async def reconcile_publish(
        self,
        request: ReconcileRequest,
    ) -> ReconcileResult: ...
```

## 12.3 Error Types

```python
UnsupportedCapabilityError
UnknownCapabilityError
AuthenticationRequiredError
AuthorizationExpiredError
RateLimitedError
PlatformTemporaryError
PlatformPermanentError
PublishUncertainError
PolicyBlockedError
```

## 12.4 Adapter Rules

- `UNKNOWN` 不等于 `SUPPORTED`。
- `comment_reply` 不得作为 `top_level_comment` 使用。
- Adapter 不得在内部回退到浏览器自动化。
- 外部请求必须有 timeout、trace_id 和结构化日志。
- 真实 Adapter 必须有 `CAPABILITIES.md`。

## 12.5 Initial Capability Defaults

```text
MockPlatformAdapter:
  all test capabilities = SUPPORTED

DouyinAdapter:
  verified official read/reply capabilities = CONDITIONAL or AUTH_REQUIRED
  arbitrary third-party top-level comment = UNKNOWN

XiaohongshuAdapter:
  social creator monitoring / third-party top-level comment = UNKNOWN

WechatChannelsAdapter:
  social creator monitoring / third-party top-level comment = UNKNOWN
```

真实能力以 `PLATFORM_CAPABILITIES.md` 和各 Adapter 的 `CAPABILITIES.md` 为准。

---

# 13. Mock Platform

## 13.1 Purpose

Mock Platform 是第一个必须完整实现的平台，用于在没有真实平台权限时验证整个产品。

## 13.2 Mock Entities

```text
MockCreator
MockPost
MockComment
MockPlatformPolicy
MockFailureProfile
```

## 13.3 Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/mock/creators` | 创建 Creator |
| POST | `/api/v1/mock/posts` | Creator 发布新 Post |
| GET | `/api/v1/mock/posts/{post_id}` | 读取 Post |
| POST | `/api/v1/mock/posts/{post_id}/comments` | 发布 Comment |
| POST | `/api/v1/mock/posts/{post_id}/simulate-comments` | 模拟其他用户评论 |
| GET | `/api/v1/mock/posts/{post_id}/comments` | 读取评论列表 |
| POST | `/api/v1/mock/failure-profile` | 配置失败注入 |
| POST | `/api/v1/mock/capabilities` | 修改能力状态 |
| POST | `/api/v1/mock/reset` | 清理 Mock 数据 |

## 13.4 Comment Ranking

Chronological Rank：

```python
def chronological_rank(comments: list[MockComment], comment_id: UUID) -> int:
    ordered = sorted(comments, key=lambda x: (x.created_at, str(x.id)))
    return next(i for i, item in enumerate(ordered, start=1) if item.id == comment_id)
```

Visible Rank 模拟策略：

```text
CHRONOLOGICAL
LIKES_WEIGHTED
AUTHOR_PINNED
PERSONALIZED_RANDOM_SEEDED
```

Mock 的随机排序必须使用固定 seed，保证测试可复现。

## 13.5 Failure Injection

```text
request_latency_ms
visibility_delay_ms
webhook_delay_ms
timeout_rate
http_429_rate
http_500_rate
token_expired
publish_success_but_timeout_rate
duplicate_webhook_rate
out_of_order_event_rate
```

---

# 14. Creator Monitor

## 14.1 Components

```text
CreatorScheduler
CreatorMonitor
AdaptivePollingPolicy
PlatformRateLimiter
DetectionDeduplicator
```

## 14.2 Poll Workflow

```text
load creator
→ verify monitor_state
→ load platform capability
→ acquire platform quota token
→ adapter.get_latest_posts
→ compare external_post_id and published_at
→ insert unseen posts
→ write outbox events
→ update last_checked_at
→ compute next_poll_at
```

## 14.3 Redis Schedule

使用 Sorted Set：

```text
key: poll_schedule:{platform}
score: unix timestamp of next_poll_at
member: creator_platform_account_id
```

Scheduler 每 500ms：

1. 原子读取到期成员。
2. 从 ZSET 移除。
3. 发送到对应 Queue。
4. Worker 完成后重新计算并加入下一次时间。

需要使用 Lua Script 或 Redis Transaction 避免多 Scheduler 重复取任务。

## 14.4 Lock

```text
poll_lock:{creator_platform_account_id}
TTL = max(expected_request_timeout * 2, 30s)
```

若未获得 Lock，任务直接 ACK，不重复请求。

---

# 15. Adaptive Polling

## 15.1 Inputs

```text
creator.priority
creator.expected_publish_windows
creator.last_post_at
creator.last_checked_at
recent_post_intervals
recent_activity_score
failure_count
platform_rate_limit_pressure
capability_status
```

## 15.2 Algorithm

```python
def next_poll_interval(ctx: PollingContext) -> int:
    if ctx.monitor_paused:
        return 3600

    if ctx.capability_status not in {
        CapabilityStatus.SUPPORTED,
        CapabilityStatus.CONDITIONAL,
        CapabilityStatus.AUTH_REQUIRED,
    }:
        return 3600

    if ctx.auth_invalid:
        return 1800

    base = ctx.normal_interval_sec

    if ctx.in_expected_publish_window:
        base = ctx.warm_interval_sec

    if ctx.priority >= 90 and ctx.in_high_probability_window:
        base = ctx.hot_interval_sec

    if ctx.recent_activity_score >= 0.8:
        base = min(base, ctx.warm_interval_sec)

    if ctx.failure_count > 0:
        base = max(base, min(3600, 2 ** ctx.failure_count * 15))

    if ctx.platform_rate_limit_pressure >= 0.8:
        base = int(base * 2.5)

    jitter = deterministic_jitter(
        entity_id=ctx.creator_platform_account_id,
        percent=0.15,
    )
    return clamp(int(base * jitter), 5, 3600)
```

## 15.3 Deterministic Jitter

Jitter 目的：避免惊群，不用于伪装人类行为。

```python
factor = 0.85 + (stable_hash(entity_id, current_hour) % 3000) / 10000
```

## 15.4 Default Intervals

```text
normal = 600s
warm = 60s
hot = 10s
burst = 5s, maximum 120s
```

任何低于 10 秒的真实平台配置都必须由 Capability Owner 明确批准。

---

# 16. Event System

## 16.1 Event Envelope

```json
{
  "event_id": "uuid",
  "event_type": "post.detected",
  "event_version": 1,
  "occurred_at": "2026-09-02T10:00:00Z",
  "observed_at": "2026-09-02T10:00:03Z",
  "platform": "MOCK",
  "creator_id": "uuid",
  "post_id": "uuid",
  "campaign_id": null,
  "trace_id": "uuid",
  "correlation_id": "uuid",
  "idempotency_key": "string",
  "payload": {}
}
```

## 16.2 Event Types

```text
creator.poll.requested
creator.poll.started
creator.poll.completed
creator.poll.failed
post.detected
post.fetch.started
post.fetch.completed
post.normalized
post.analysis.started
post.analysis.completed
post.skipped
comment.generation.started
comment.generated
comment.quality.started
comment.quality.completed
risk.check.started
risk.check.completed
review.requested
review.completed
comment.publish.requested
comment.publish.started
comment.publish.uncertain
comment.published
comment.publish.failed
comment.reconciled
```

## 16.3 Outbox Delivery

- Relay 每 250ms 拉取未发布 Event。
- 使用 `FOR UPDATE SKIP LOCKED`。
- 成功入 Queue 后设置 `published_at`。
- 连续失败进入告警，但不删除 Event。

## 16.4 Queue Mapping

```text
critical:
  post.detected
  comment.publish.requested

high:
  creator.poll for priority >= 90
  comment.generation.started in FIRST_COMMENT mode

normal:
  standard polling
  normal analysis

low:
  analytics aggregation
  historical reconciliation
```

---

# 17. Fast Path

## 17.1 Trigger

满足以下条件进入 FAST：

```text
campaign.run_mode in {FAST, FIRST_COMMENT, TOP5_COMMENT}
AND post.caption or title is available
AND creator relationship is allowed
AND no hard policy block
```

## 17.2 Pipeline

```text
Post Detected
→ Metadata Normalize
→ Rule Keyword Filter
→ Concrete Anchor Extraction
→ Opportunity Rules + Small LLM
→ Generate 2 Short Candidates in one call
→ Deterministic Quality Rules
→ Rule Risk Engine
→ LLM Risk only if uncertainty requires
→ Official Publish or Review
```

## 17.3 Latency Rules

FAST 不等待：

- 完整视频下载
- 完整 ASR
- 大型多模态模型
- 历史全量评论抓取

但必须等待：

- Capability Check
- Identity Check
- Concrete Anchor
- Claim Check
- Duplicate Check
- Hard Risk Rules

## 17.4 Fallback

以下情况进入 SLOW：

```text
anchor confidence < 0.6
caption too short and no visual summary
content relevance uncertain
brand mention requires additional evidence
sensitive product claim appears
```

## 17.5 Timeout

```text
anchor extraction: 500ms
opportunity: 900ms
comment generation: 1800ms
quality rules: 200ms
risk rules: 200ms
```

超时策略：

- 不使用未经上下文验证的备用模板。
- FIRST_COMMENT 模式超时后转 Review/Skip，而不是发布通用评论。

---

# 18. Slow Path

## 18.1 Inputs

```text
Full Caption
Images
OCR
Thumbnail
Partial / Full Transcript
Visual Summary
Existing Comments（如果官方能力允许）
```

## 18.2 Use Cases

- NORMAL 模式
- FAST 低置信度
- 高价值 Partner Creator
- Product Claim 需要确认
- 图像或视频是主要语义载体

## 18.3 Processing Order

```text
OCR first
→ thumbnail vision
→ partial ASR
→ full ASR only if still uncertain
→ multimodal model last
```

## 18.4 Storage

- 保存模型派生摘要，不默认永久保存完整第三方视频。
- 媒体 Retention 由平台授权和公司政策控制。

---

# 19. Opportunity Agent

## 19.1 Structured Output

```python
class OpportunityScore(BaseModel):
    creator_value: float = Field(ge=0, le=100)
    relevance: float = Field(ge=0, le=100)
    audience_match: float = Field(ge=0, le=100)
    traffic_potential: float = Field(ge=0, le=100)
    post_velocity: float = Field(ge=0, le=100)
    brand_fit: float = Field(ge=0, le=100)
    commercial_risk: float = Field(ge=0, le=100)
    platform_risk: float = Field(ge=0, le=100)
    final_score: float = Field(ge=0, le=100)
    reason_codes: list[str]
    recommended_strategy: CommentStrategy
```

## 19.2 Formula

```python
final_score = (
    0.18 * creator_value
    + 0.22 * relevance
    + 0.15 * audience_match
    + 0.12 * traffic_potential
    + 0.08 * post_velocity
    + 0.15 * brand_fit
    - 0.05 * commercial_risk
    - 0.05 * platform_risk
)
```

## 19.3 Relationship Multiplier

```text
OWN_ACCOUNT = 1.10
PARTNER_CREATOR = 1.05
OFFICIAL_CAMPAIGN_CREATOR = 1.05
GENERAL_CREATOR = 0.90
BRAND_ACCOUNT = 0.70
COMPETITOR = 0.00
BLOCKED_CREATOR = 0.00
```

## 19.4 Decision

```text
>= 80: HIGH_PRIORITY_CANDIDATE
65–79: REVIEW_CANDIDATE
45–64: SLOW_PATH_OR_SKIP
< 45: SKIP
```

Hard Rules 始终覆盖评分。

---

# 20. Comment Agent

## 20.1 Interface

```python
async def generate_comments(
    *,
    brand: BrandContext,
    account_identity: AccountIdentityContext,
    voice_profile: VoiceProfileContext,
    campaign: CampaignContext,
    creator: CreatorContext,
    post: PostContext,
    anchors: list[PostAnchorContext],
    strategy: CommentStrategy,
    recent_comments: list[str],
    count: int = 2,
) -> GeneratedCommentBatch:
    ...
```

## 20.2 Output

```python
class GeneratedComment(BaseModel):
    comment: str
    strategy: CommentStrategy
    referenced_anchor_ids: list[UUID]
    referenced_claim_ids: list[UUID]
    relevance_score: float
    commercial_score: float
    confidence: float
    generation_reason: str
    uses_first_person_experience: bool
    implies_consumer_identity: bool

class GeneratedCommentBatch(BaseModel):
    candidates: list[GeneratedComment]
    prompt_version: str
    model_provider: str
    model_name: str
```

## 20.3 Prompt Requirements

System Prompt 必须包含：

```text
You are writing on behalf of the declared account identity.
Do not pretend to be an ordinary consumer.
Do not invent purchase, usage, demographic or personal experiences.
Use at least one provided post anchor.
Do not use generic praise if a concrete observation is possible.
Do not attack or compare against competitors.
Do not add contact information or off-platform calls to action.
Only use approved claims.
Do not insert intentional typos or awkwardness to appear human.
```

## 20.4 Comment Strategies

### NORMAL_INTERACTION

- 不提品牌。
- 基于具体穿搭、颜色、版型、场景等锚点。
- 适用于 GENERAL_CREATOR 的默认策略。

### EXPERT_COMMENT

- 提供真实、可验证的材质或搭配知识。
- 不使用绝对化、医疗化或无法证明的声明。

### LIGHT_BRAND_MENTION

- 仅 Partner / Campaign 允许。
- 需要品牌身份可识别。
- 默认人工审核。

### PARTNER_BRAND_COMMENT

- 适用于正式合作 Creator。
- 评论文本遵循 Campaign 披露模板，但仍锚定具体内容。

### PRODUCT_RELATED

- 仅使用 Approved Claim。
- 禁止伪造使用体验。

### CAMPAIGN_DISCLOSURE

- 明确表达合作或品牌身份。
- 不以普通消费者口吻推荐。

## 20.5 “自然度”实现方式

允许的质量手段：

- 使用具体帖子锚点。
- 使用多个批准的句式结构。
- 根据平台长度、标点和 Emoji 规范调整。
- 根据真实 Brand Voice 调整用词。
- 与近期评论做重复和相似度检查。
- 由人工编辑和回馈持续改进 Prompt。

禁止的“自然度”手段：

- 故意加入错别字、病句、网络口头禅以欺骗检测。
- 随机模拟打字速度、在线时间或人类作息。
- 建立虚构消费者 Persona。
- 根据 AI Detector 分数反复改写。
- 隐藏 AI 内容来源或平台要求的标识。

## 20.6 Recent Comment Retrieval

MVP 拉取最近：

```text
same brand_account: 100 comments
same campaign: 100 comments
same creator: 20 comments
```

用于重复检查和避免持续使用相同开头。

---

# 21. Authenticity & Quality Evaluator

## 21.1 Purpose

该模块负责“评论质量像真人认真读过内容”，而不是“把机器伪装成人”。

## 21.2 Rule Checks

```text
has_anchor
anchor_text_supported_by_post
not_generic_only
no_fake_experience
no_fake_identity
no_unapproved_claim
not_competitor_attack
no_external_contact
within_platform_length
no_duplicate
no_near_duplicate
voice_profile_compliant
no_intentional_typo_pattern
```

## 21.3 Scoring

```python
quality_score = (
    0.25 * anchor_coverage
    + 0.20 * specificity
    + 0.15 * fluency
    + 0.15 * voice_match
    + 0.15 * novelty
    + 0.10 * truthfulness
)
```

## 21.4 Decision

```text
Hard Truthfulness / Identity Failure → BLOCK
quality_score >= 0.80 and duplicate_similarity < 0.70 → ALLOW
quality_score >= 0.65 → REVIEW
otherwise → REGENERATE_ONCE or SKIP
```

FIRST_COMMENT 模式最多自动 Regenerate 一次；第二次失败直接 Review/Skip。

## 21.5 Similarity MVP

```text
exact normalized match
character 3-gram Jaccard
word 2-gram Jaccard
same prefix signature
same CTA signature
```

建议阈值：

```text
similarity >= 0.90 → BLOCK
0.82 <= similarity < 0.90 → REVIEW
```

这些阈值用于反垃圾和内容质量，不用于对抗平台检测。

## 21.6 Metrics

```text
anchor_coverage_rate
specific_comment_rate
generic_comment_block_rate
fake_experience_block_rate
duplicate_block_rate
human_acceptance_rate
human_edit_rate
median_edit_distance
post_publish_removal_rate
```

明确禁止：

```text
ai_detector_pass_rate
human_probability
stealth_score
```

---

# 22. Risk Agent

## 22.1 Two Layers

```text
RuleRiskEngine
→ LLMRiskAgent（仅处理语义不确定项）
```

## 22.2 Hard Rules

```text
creator.relationship in {COMPETITOR, BLOCKED_CREATOR}
unsupported platform capability for requested action
fake consumer experience
fake account identity
unapproved product claim
external contact / off-platform diversion
prohibited phrase
daily account limit exceeded
creator daily limit exceeded
duplicate idempotency key
publisher kill switch enabled
AI disclosure required but unresolved
```

## 22.3 LLM Risk Output

```python
class RiskAssessment(BaseModel):
    decision: RiskDecision
    risk_score: float = Field(ge=0, le=1)
    reasons: list[str]
    matched_policy_categories: list[str]
    required_actions: list[str]
```

## 22.4 Policy

```text
risk < 0.30 → ALLOW if all hard gates pass
0.30–0.65 → REVIEW
> 0.65 → BLOCK or REVIEW depending rule category
```

Identity deception、fake experience、capability bypass 一律 BLOCK。

## 22.5 Fail Closed

以下任意情况不得自动发布：

```text
Risk Agent unavailable
Policy version expired
Identity profile missing
Capability registry unavailable
Brand claims unavailable
Disclosure requirement unresolved
```

---

# 23. Publishing System

## 23.1 Publish Modes

```python
class PublishMode(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    OFFICIAL_PARTNER = "OFFICIAL_PARTNER"
    MANUAL = "MANUAL"
    UNSUPPORTED = "UNSUPPORTED"
```

## 23.2 Router

```python
async def route_publish(job: PublishJobContext) -> PublishRoute:
    capabilities = await registry.get(job.platform)

    if job.kill_switch_enabled:
        return PublishRoute.blocked("KILL_SWITCH")

    if capabilities.top_level_comment == CapabilityStatus.SUPPORTED:
        return PublishRoute.official_api()

    if capabilities.top_level_comment == CapabilityStatus.CONDITIONAL:
        if job.authorization_satisfies_conditions:
            return PublishRoute.official_api()
        return PublishRoute.manual("AUTH_OR_SCOPE_MISSING")

    if capabilities.top_level_comment in {
        CapabilityStatus.UNKNOWN,
        CapabilityStatus.MANUAL,
        CapabilityStatus.UNSUPPORTED,
    }:
        return PublishRoute.manual("TOP_LEVEL_COMMENT_NOT_VERIFIED")

    return PublishRoute.blocked("PLATFORM_DISABLED")
```

## 23.3 Publish Preconditions

```text
state == READY
final RiskDecision == ALLOW
quality decision == ALLOW
identity profile active
campaign active
account auth valid
capability snapshot current
idempotency lock acquired
rate limit token acquired
```

## 23.4 Publish Timeout

若网络 Timeout 但可能已经发布：

```text
PUBLISHING
→ PUBLISH_UNCERTAIN
→ reconcile_publish
→ PUBLISHED or READY_FOR_RETRY
```

不得直接重试。

## 23.5 Manual Publish Workflow

Manual Job 包含：

```text
post URL
creator
post preview
final approved comment
copy button
open platform button
identity disclosure guidance
AI disclosure guidance
operator confirmation checkbox
published / skipped / failed result
optional external_comment_id
```

---

# 24. Human Review

## 24.1 Review Queue Rules

默认进入 Review：

```text
GENERAL_CREATOR + any brand mention
quality_score 0.65–0.80
risk_score 0.30–0.65
AI disclosure unknown
manual publish capability
first-person language
product claim present
```

## 24.2 API

```http
GET  /api/v1/review/jobs
GET  /api/v1/review/jobs/{job_id}
POST /api/v1/review/jobs/{job_id}/approve
POST /api/v1/review/jobs/{job_id}/edit-and-approve
POST /api/v1/review/jobs/{job_id}/reject
POST /api/v1/review/jobs/{job_id}/claim
```

## 24.3 UI Fields

```text
Creator and Relationship
Publishing Account and Identity
Post Time / Detection Time
Post Preview
Concrete Anchors
Opportunity Score
Candidate Comments
Duplicate Similarity
Quality Breakdown
Risk Reasons
Approved Claims
Disclosure Requirement
Capability Status
```

## 24.4 Edit Audit

保存：

```text
original_candidate_text
final_text
reviewer_id
edit_distance
edit_reason
resolved_at
```

人工编辑后的 Content Provenance 更新为：

```text
AI_ASSISTED_HUMAN_EDITED
```

---

# 25. API Specification

所有 API 前缀：

```text
/api/v1
```

统一错误：

```json
{
  "error": {
    "code": "UNSUPPORTED_CAPABILITY",
    "message": "Top-level comment is not verified for this platform.",
    "trace_id": "uuid",
    "details": {}
  }
}
```

## 25.1 Auth

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| POST | `/auth/login` | email, password | access_token, user | 200/401 |
| GET | `/auth/me` | bearer token | user | 200/401 |

## 25.2 Brands

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| POST | `/brands` | BrandCreate | BrandRead | 201/422 |
| GET | `/brands` | filters | Page[BrandRead] | 200 |
| GET | `/brands/{id}` | — | BrandRead | 200/404 |
| PATCH | `/brands/{id}` | BrandUpdate | BrandRead | 200/404 |

## 25.3 Products

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| POST | `/products` | ProductCreate | ProductRead | 201 |
| GET | `/products` | brand_id | Page | 200 |
| PATCH | `/products/{id}` | ProductUpdate | ProductRead | 200/404 |

## 25.4 Campaigns

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| POST | `/campaigns` | CampaignCreate | CampaignRead | 201 |
| POST | `/campaigns/{id}/activate` | — | CampaignRead | 200/409 |
| POST | `/campaigns/{id}/pause` | — | CampaignRead | 200 |
| GET | `/campaigns/{id}/metrics` | range | metrics | 200 |

## 25.5 Creators

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| POST | `/creators` | CreatorCreate | CreatorRead | 201 |
| GET | `/creators` | platform, relationship, state | Page | 200 |
| PATCH | `/creators/{id}` | CreatorUpdate | CreatorRead | 200 |
| POST | `/creators/{id}/monitor` | — | MonitorState | 200/409 |
| POST | `/creators/{id}/pause` | — | MonitorState | 200 |
| POST | `/creators/{id}/poll-now` | — | TaskReceipt | 202/429 |

## 25.6 Platform Accounts

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| POST | `/platform-accounts` | account + identity + voice | AccountRead | 201 |
| GET | `/platform-accounts` | platform | Page | 200 |
| POST | `/platform-accounts/{id}/verify-auth` | — | AuthStatus | 200/401 |
| POST | `/platform-accounts/{id}/kill-switch` | enabled | AccountRead | 200 |

## 25.7 Posts

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| GET | `/posts` | filters | Page[PostRead] | 200 |
| GET | `/posts/{id}` | — | PostDetail | 200/404 |
| POST | `/posts/{id}/reanalyze` | mode | TaskReceipt | 202/409 |
| GET | `/posts/{id}/timeline` | — | Timeline | 200 |

## 25.8 Comments

| Method | Path | Request | Response | Status |
|---|---|---|---|---|
| GET | `/comments/candidates` | status | Page | 200 |
| GET | `/comments/published` | filters | Page | 200 |
| POST | `/comments/candidates/{id}/regenerate` | reason | CandidateBatch | 200/409 |
| POST | `/comments/{id}/reconcile` | — | PublishResult | 202 |

## 25.9 Review

见第 24 节。

## 25.10 Metrics

| Method | Path | Purpose |
|---|---|---|
| GET | `/metrics/overview` | 核心 KPI |
| GET | `/metrics/latency` | P50/P90/P95/P99 |
| GET | `/metrics/quality` | 质量与人工编辑 |
| GET | `/metrics/ranking` | First / Top5 + Coverage |

## 25.11 System

| Method | Path | Purpose |
|---|---|---|
| GET | `/system/health` | liveness |
| GET | `/system/readiness` | DB/Redis/Worker readiness |
| GET | `/system/queues` | Queue depth |
| GET | `/system/capabilities` | Capability Matrix |
| POST | `/system/publishers/{platform}/disable` | Platform kill switch |

## 25.12 Events

```http
GET /api/v1/events/stream
Content-Type: text/event-stream
```

支持参数：

```text
creator_id
post_id
campaign_id
event_type
```

## 25.13 Mock

见第 13 节。

---

# 26. Frontend

## 26.1 Routes

```text
/dashboard
/creators
/live
/posts
/review
/comments
/campaigns
/brand
/accounts
/risk
/analytics
/settings
```

## 26.2 Live Page

实时展示：

```text
Creator
Relationship
Post Time
Detection Time
Detection Latency
Current Stage
Extracted Anchors
Candidate Comment
Quality Score
Risk Decision
Publish Mode
Publish Result
Comment Rank
```

## 26.3 Review Page

必须支持：

```text
keyboard shortcut 1/2/3 select candidate
E edit
A approve
S skip
open post
copy comment
```

快捷键不能绕过确认规则。

## 26.4 Account Page

展示：

```text
Account Kind
Public Identity Text
Auto Publish Enabled
Disclosure Policy
Authentication Status
Daily Limit
Kill Switch
```

## 26.5 Capability Page

每个平台显示：

```text
Capability
Status
Verification Source
Verified At
Expires At
Conditions
Owner
```

---

# 27. State Machine

## 27.1 Allowed Transitions

```python
ALLOWED_TRANSITIONS = {
    DISCOVERED: {FETCHING, SKIPPED, BLOCKED},
    FETCHING: {ANALYZING, FAILED, SKIPPED},
    ANALYZING: {GENERATING, SKIPPED, BLOCKED, FAILED},
    GENERATING: {QUALITY_CHECKING, FAILED},
    QUALITY_CHECKING: {RISK_CHECKING, WAITING_REVIEW, BLOCKED, FAILED},
    RISK_CHECKING: {WAITING_REVIEW, READY, BLOCKED, FAILED},
    WAITING_REVIEW: {READY, SKIPPED, BLOCKED},
    READY: {PUBLISHING, WAITING_MANUAL_PUBLISH, BLOCKED},
    WAITING_MANUAL_PUBLISH: {PUBLISHING, PUBLISHED, SKIPPED, FAILED},
    PUBLISHING: {PUBLISHED, PUBLISH_UNCERTAIN, FAILED},
    PUBLISH_UNCERTAIN: {PUBLISHED, READY, FAILED},
    PUBLISHED: set(),
    SKIPPED: set(),
    BLOCKED: set(),
    FAILED: set(),
}
```

## 27.2 Transition API

```python
def transition(job: CommentJob, target: CommentJobState, reason: str) -> None:
    if target not in ALLOWED_TRANSITIONS[job.state]:
        raise InvalidStateTransition(job.state, target)
    job.state = target
    job.state_reason = reason
```

任何 Service 不得直接赋值 `job.state`。

## 27.3 Diagram

```mermaid
stateDiagram-v2
    [*] --> DISCOVERED
    DISCOVERED --> FETCHING
    DISCOVERED --> SKIPPED
    DISCOVERED --> BLOCKED
    FETCHING --> ANALYZING
    FETCHING --> FAILED
    ANALYZING --> GENERATING
    ANALYZING --> SKIPPED
    ANALYZING --> BLOCKED
    GENERATING --> QUALITY_CHECKING
    QUALITY_CHECKING --> RISK_CHECKING
    QUALITY_CHECKING --> WAITING_REVIEW
    QUALITY_CHECKING --> BLOCKED
    RISK_CHECKING --> READY
    RISK_CHECKING --> WAITING_REVIEW
    RISK_CHECKING --> BLOCKED
    WAITING_REVIEW --> READY
    WAITING_REVIEW --> SKIPPED
    READY --> PUBLISHING
    READY --> WAITING_MANUAL_PUBLISH
    PUBLISHING --> PUBLISHED
    PUBLISHING --> PUBLISH_UNCERTAIN
    PUBLISHING --> FAILED
    PUBLISH_UNCERTAIN --> PUBLISHED
    PUBLISH_UNCERTAIN --> READY
    WAITING_MANUAL_PUBLISH --> PUBLISHED
```

---

# 28. Metrics

## 28.1 Timeline Timestamps

```text
post_created_at
detected_at
fetch_started_at
fetch_completed_at
analysis_started_at
analysis_completed_at
generation_started_at
generation_completed_at
quality_started_at
quality_completed_at
risk_started_at
risk_completed_at
review_started_at
review_completed_at
publish_started_at
published_at
rank_observed_at
```

## 28.2 Latency Metrics

```text
detection_latency_ms
fetch_latency_ms
analysis_latency_ms
generation_latency_ms
quality_latency_ms
risk_latency_ms
review_latency_ms
publish_latency_ms
end_to_end_latency_ms
```

## 28.3 Ranking Metrics

```text
first_comment_success_rate
top5_success_rate
chronological_rank_measurement_coverage
visible_rank_measurement_coverage
```

不可观测不算失败。

## 28.4 Quality Metrics

```text
anchor_coverage_rate
quality_allow_rate
quality_review_rate
quality_block_rate
generic_comment_block_rate
duplicate_block_rate
fake_experience_block_rate
human_acceptance_rate
human_edit_rate
median_edit_distance
comment_removal_rate
```

## 28.5 Forbidden Metrics

```text
AI detector pass rate
human probability score
stealth success rate
review evasion rate
```

## 28.6 Prometheus Names

```text
firstcomment_detection_latency_seconds
firstcomment_generation_latency_seconds
firstcomment_publish_latency_seconds
firstcomment_jobs_total{state=...}
firstcomment_risk_decisions_total{decision=...}
firstcomment_quality_decisions_total{decision=...}
firstcomment_queue_depth{queue=...}
firstcomment_publish_total{platform=...,result=...}
firstcomment_rank_measurement_total{type=...,confidence=...}
```

---

# 29. Reliability

## 29.1 Retry Matrix

| Failure | Retry | Action |
|---|---:|---|
| HTTP 500/502/503 | Yes | exponential backoff + jitter |
| HTTP 429 | Yes | respect Retry-After |
| Auth expired | No immediate | pause account + notify |
| Unsupported capability | No | manual / unsupported |
| LLM timeout | Once | alternate approved provider or review |
| Invalid structured output | Once | repair prompt; then review |
| Risk service unavailable | No auto publish | fail closed |
| Publish timeout | No direct retry | reconcile first |
| Duplicate key | No | treat existing record as source of truth |

## 29.2 Circuit Breaker

按 `(platform, operation)` 维度：

```text
CLOSED
OPEN
HALF_OPEN
```

触发示例：

```text
5 consecutive platform failures
or 50% failure in rolling 20 requests
```

OPEN 时不尝试隐藏性替代路径。

## 29.3 Dead Letter

```text
dead_letter_jobs
- source_queue
- actor_name
- payload
- error
- attempts
- first_failed_at
- last_failed_at
- trace_id
```

## 29.4 Reconciliation

定时任务检查：

```text
PUBLISH_UNCERTAIN older than 30s
PUBLISHING older than timeout
WAITING_REVIEW expired
outbox unpublished older than 60s
```

---

# 30. Security

## 30.1 Authentication and RBAC

Roles：

```text
ADMIN
BRAND_MANAGER
REVIEWER
VIEWER
```

权限：

- 只有 ADMIN 可修改 Capability 和 Kill Switch。
- BRAND_MANAGER 可修改 Brand、Campaign 和 Voice。
- REVIEWER 可审核，不可修改平台 Token。
- VIEWER 只读。

## 30.2 Token Encryption

- 使用 AES-256-GCM。
- Master Key 来自环境变量或 Secret Manager。
- 数据库存 `ciphertext + nonce + key_version`。
- 日志永不输出 Token。

## 30.3 Audit

以下行为必须记录：

```text
login
failed login
role change
credential update
identity profile update
voice profile update
review decision
comment edit
publish action
kill switch change
capability change
```

## 30.4 AI Content Provenance

- 内部始终记录 Comment Provenance。
- 平台或法律要求 AI 声明时，工作流必须支持并提示。
- 不提供删除、隐藏、篡改 AI 标识的代码路径。
- 若披露要求不明确，转人工审核而不是默认隐藏。

## 30.5 Privacy

- 不建立普通用户敏感画像。
- 不存储不必要的个人信息。
- 媒体和第三方内容按 Retention Policy 清理。

---

# 31. Testing

## 31.1 Unit Tests

```text
state machine transitions
opportunity formula
relationship multiplier
poll interval and backoff
jitter determinism
idempotency key
comment normalization
n-gram similarity
anchor requirement
fake experience rules
identity consistency
risk rules
publish router
rank calculation
```

## 31.2 Integration Tests

```text
PostgreSQL migrations
repository transactions
outbox relay
Redis schedule
Dramatiq actors
Mock adapter
SSE event stream
credential encryption round-trip
```

## 31.3 Contract Tests

每个 Adapter：

```text
get_capabilities returns all fields
unsupported method raises UnsupportedCapabilityError
reply is not treated as top-level comment
timeout maps to PlatformTemporaryError or PublishUncertainError
no adapter invokes browser automation fallback
```

每个 Agent Provider：

```text
valid structured output
invalid output repair
timeout behavior
request id persisted
prompt version persisted
```

## 31.4 Required E2E Cases

### E2E-001 First Comment

```text
Post has 0 comments
Agent publishes
Expected chronological_rank = 1
```

### E2E-002 Top5

```text
Post has 3 comments
Agent publishes
Expected chronological_rank = 4
Expected top5 = true
```

### E2E-003 Not Top5

```text
Post has 5 comments
Agent publishes
Expected rank = 6
Expected top5 = false
```

### E2E-004 Risk Block

```text
candidate contains fake consumer purchase experience
Expected BLOCK
Expected no publish job
```

### E2E-005 Identity Block

```text
BRAND_OFFICIAL account
candidate says “我买过我们家” as ordinary consumer
Expected BLOCK
```

### E2E-006 Generic Comment Review

```text
candidate = “好好看，支持一下”
no concrete anchor
Expected REVIEW or regenerate
```

### E2E-007 Duplicate

```text
same normalized comment recently published
Expected BLOCK
```

### E2E-008 Unsupported Platform

```text
top_level_comment capability = UNKNOWN
Expected WAITING_MANUAL_PUBLISH
```

### E2E-009 Retry Idempotency

```text
publish succeeds but response times out
reconcile returns published
Expected exactly one external comment
```

### E2E-010 AI Disclosure Pending

```text
disclosure policy requires review
status = REQUIRED_PENDING
Expected no auto publish
```

### E2E-011 Kill Switch

```text
platform kill switch enabled
Expected BLOCK before external call
```

### E2E-012 Full Demo

```text
create brand
create identity and voice
create campaign
create creator
activate monitor
mock creator publishes
monitor detects
anchors extracted
comment generated
quality and risk pass
mock publish
rank calculated
SSE timeline displayed
```

## 31.5 Commands

```bash
make lint
make typecheck
make test-unit
make test-integration
make test-e2e
make test
```

---

# 32. Deployment

## 32.1 Docker Compose Services

```text
postgres
redis
minio
backend-api
worker-critical
worker-default
worker-low
scheduler
outbox-relay
frontend
prometheus
```

Grafana 可作为可选 Profile。

## 32.2 `.env.example`

```dotenv
APP_ENV=development
APP_SECRET_KEY=
DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/firstcomment
REDIS_URL=redis://redis:6379/0
TOKEN_ENCRYPTION_KEY=

LLM_PROVIDER=mock
LLM_API_KEY=
LLM_MODEL_FAST=
LLM_MODEL_NORMAL=
LLM_TIMEOUT_SECONDS=5

AUTO_PUBLISH_DEFAULT=false
RISK_ALLOW_THRESHOLD=0.30
RISK_BLOCK_THRESHOLD=0.65
QUALITY_ALLOW_THRESHOLD=0.80
QUALITY_REVIEW_THRESHOLD=0.65
DUPLICATE_BLOCK_THRESHOLD=0.90
DUPLICATE_REVIEW_THRESHOLD=0.82

COMMENT_MODE=REVIEW
SSE_HEARTBEAT_SECONDS=15
LOG_LEVEL=INFO
```

## 32.3 Startup

```bash
cp .env.example .env
docker compose up --build
make migrate
make seed-demo
```

## 32.4 Health

```text
/api/v1/system/health
/api/v1/system/readiness
```

Readiness 需检查：

```text
PostgreSQL
Redis
Outbox Relay heartbeat
Critical Worker heartbeat
```

---

# 33. Development Phases

## Phase 0 — Governance and Bootstrap

目标：建立安全边界、仓库、工具链和运行骨架。

## Phase 1 — Core Domain and Database

目标：实现枚举、ORM、Migration、Repository 和状态机。

## Phase 2 — Mock Platform

目标：实现可模拟 Post、Comment、排名和错误的平台。

## Phase 3 — Queue, Scheduler and Event Pipeline

目标：实现 Dramatiq、Redis ZSET、Outbox 和 Timeline。

## Phase 4 — Creator Monitor

目标：实现动态 Polling、去重和新 Post 检测。

## Phase 5 — Content and Opportunity Pipeline

目标：规范化内容、提取锚点、评分和路径路由。

## Phase 6 — Comment and Quality Layer

目标：实现 Structured Generation、Brand Voice、身份一致性和去模板化质量检查。

## Phase 7 — Risk and Review

目标：实现 Rule Risk、LLM Risk 和人工审核。

## Phase 8 — Publishing and Idempotency

目标：实现 Router、Mock Publish、Manual Workflow 和 Reconciliation。

## Phase 9 — Fast Path and Latency

目标：优化 First Comment 路径并加入完整延迟指标。

## Phase 10 — Frontend and SSE

目标：实现 Live、Review、Capabilities 和 Analytics 页面。

## Phase 11 — Reliability, Security and E2E

目标：错误注入、Circuit Breaker、加密、审计和 DoD E2E。

## Phase 12 — Real Platform Adapter Skeletons

目标：建立严格能力文档和官方 API Adapter 骨架，不实现未经验证能力。

---

# 34. Detailed Tasks

下面每项设计为 30 分钟到数小时内可独立完成。

## Phase 0

### Task 0.1 — Create repository skeleton

**Objective**：创建根目录、backend、frontend、docs、scripts。  
**Files to Create**：根目录树中的基础文件。  
**Implementation**：建立空包、README、Makefile、`.gitignore`。  
**Acceptance Criteria**：目录与本规范一致；Git working tree clean。  
**Tests**：`find . -maxdepth 3 -type f` 人工检查。  
**Dependencies**：无。

### Task 0.2 — Add NON_GOALS and capability policy

**Objective**：把禁止规避检测、伪装真人和非官方自动化写入仓库。  
**Files**：`NON_GOALS.md`、`PLATFORM_CAPABILITIES.md`。  
**Implementation**：复制本规范的边界和 Capability 状态模型。  
**Acceptance Criteria**：文档明确禁止 detector evasion、fake persona、label removal。  
**Tests**：Documentation review checklist。  
**Dependencies**：0.1。

### Task 0.3 — Backend tooling

**Objective**：配置 Python 项目。  
**Files**：`backend/pyproject.toml`。  
**Implementation**：FastAPI、SQLAlchemy、Alembic、Pydantic、Dramatiq、Redis、httpx、pytest、Ruff、mypy。  
**Acceptance Criteria**：`ruff check .` 和 `mypy app` 可运行。  
**Tests**：`make lint && make typecheck`。  
**Dependencies**：0.1。

### Task 0.4 — Frontend tooling

**Objective**：初始化 Next.js TypeScript strict 项目。  
**Files**：`frontend/*`。  
**Acceptance Criteria**：`npm run build` 成功。  
**Tests**：`npm run lint`。  
**Dependencies**：0.1。

### Task 0.5 — Docker Compose baseline

**Objective**：启动 PostgreSQL、Redis、API、Frontend。  
**Files**：`docker-compose.yml`、`.env.example`。  
**Acceptance Criteria**：`docker compose up` 后 health endpoint 200。  
**Tests**：curl health。  
**Dependencies**：0.3、0.4。

## Phase 1

### Task 1.1 — Core config and logging

**Files**：`core/config.py`、`core/logging.py`、`main.py`。  
**Implementation**：Pydantic Settings、JSON logs、trace_id middleware。  
**Acceptance Criteria**：每个请求日志有 trace_id。  
**Tests**：`tests/unit/core/test_config.py`、API log integration test。  
**Dependencies**：0.3。

### Task 1.2 — Database session and Alembic

**Files**：`db/base.py`、`db/session.py`、`alembic.ini`、`migrations/env.py`。  
**Acceptance Criteria**：空库 `alembic upgrade head` 成功。  
**Tests**：CI migration test。  
**Dependencies**：1.1。

### Task 1.3 — Implement enums and capabilities

**Files**：`domain/enums.py`、`domain/capabilities.py`。  
**Acceptance Criteria**：所有 Enum 与本规范一致。  
**Tests**：serialization round-trip。  
**Dependencies**：0.3。

### Task 1.4 — Implement Brand, Product, Campaign models

**Files**：对应 `models/`、`schemas/`、migration。  
**Acceptance Criteria**：CRUD schema valid；FK 和索引存在。  
**Tests**：model and repository tests。  
**Dependencies**：1.2、1.3。

### Task 1.5 — Implement Account, Identity and Voice models

**Files**：`account.py`、`identity_profile.py`、`voice_profile.py`。  
**Implementation**：加入数据库 Check Constraint，品牌官方账号不能配置普通消费者身份。  
**Acceptance Criteria**：非法组合写库失败。  
**Tests**：`test_identity_constraints.py`。  
**Dependencies**：1.4。

### Task 1.6 — Implement Creator and Post models

**Files**：`creator.py`、`post.py`、migration。  
**Acceptance Criteria**：`(platform, external_post_id)` 唯一。  
**Tests**：重复插入抛 IntegrityError。  
**Dependencies**：1.4。

### Task 1.7 — Implement Comment, Quality, Risk and Publish models

**Files**：`comment.py`、`risk.py`、`publish.py`。  
**Acceptance Criteria**：Schema 中不存在 detector-evasion 字段；idempotency_key unique。  
**Tests**：schema inspection test。  
**Dependencies**：1.5、1.6。

### Task 1.8 — Implement state machine

**Files**：`domain/state_machine.py`。  
**Acceptance Criteria**：非法迁移抛 `InvalidStateTransition`。  
**Tests**：枚举所有合法/非法迁移。  
**Dependencies**：1.3、1.7。

### Task 1.9 — Generic repositories and transaction helpers

**Files**：`repositories/base.py` 及核心 Repository。  
**Acceptance Criteria**：Service 可在单事务中写 Post + Outbox。  
**Tests**：transaction rollback test。  
**Dependencies**：1.7。

## Phase 2

### Task 2.1 — Platform base contract

**Files**：`platforms/base.py`、`platforms/errors.py`。  
**Acceptance Criteria**：定义全部方法和错误映射。  
**Tests**：abstract contract test。  
**Dependencies**：1.3。

### Task 2.2 — Platform registry

**Files**：`platforms/registry.py`。  
**Acceptance Criteria**：按 Platform 获取 Adapter；未知平台失败。  
**Tests**：registry unit tests。  
**Dependencies**：2.1。

### Task 2.3 — Mock creator and post API

**Files**：`platforms/mock/service.py`、`api/v1/mock.py`。  
**Acceptance Criteria**：可创建 Creator 和 Post。  
**Tests**：API integration tests。  
**Dependencies**：2.2、1.6。

### Task 2.4 — Mock comments and chronological ranking

**Files**：`platforms/mock/ranking.py`、Mock comment endpoints。  
**Acceptance Criteria**：0/3/5 既有评论场景排名正确。  
**Tests**：E2E-001/002/003 的基础测试。  
**Dependencies**：2.3。

### Task 2.5 — Mock visible ranking modes

**Files**：`ranking.py`。  
**Acceptance Criteria**：四种排序模式可配置且 seed 可复现。  
**Tests**：snapshot tests。  
**Dependencies**：2.4。

### Task 2.6 — Failure injection

**Files**：`failure_injection.py`。  
**Acceptance Criteria**：可模拟 latency、429、500、timeout、success-but-timeout。  
**Tests**：parameterized integration tests。  
**Dependencies**：2.3。

### Task 2.7 — MockPlatformAdapter

**Files**：`platforms/mock/adapter.py`。  
**Acceptance Criteria**：完整实现 Adapter Contract。  
**Tests**：contract suite 全通过。  
**Dependencies**：2.4、2.6。

## Phase 3

### Task 3.1 — Dramatiq broker

**Files**：`workers/broker.py`、`workers/middleware.py`。  
**Acceptance Criteria**：Worker 可消费 test actor；async actor 可运行。  
**Tests**：broker integration test。  
**Dependencies**：0.5。

### Task 3.2 — Event schema

**Files**：`domain/events.py`。  
**Acceptance Criteria**：Event Envelope 可序列化且 version 必填。  
**Tests**：schema tests。  
**Dependencies**：1.3。

### Task 3.3 — Outbox model and relay

**Files**：`models/event.py`、`repositories/outbox.py`、`workers/outbox_relay.py`。  
**Acceptance Criteria**：Outbox 只发布一次；失败可重试。  
**Tests**：concurrent relay test。  
**Dependencies**：3.1、3.2、1.9。

### Task 3.4 — Redis priority queues

**Files**：broker queue config。  
**Acceptance Criteria**：critical/high/normal/low 分开消费。  
**Tests**：priority ordering integration test。  
**Dependencies**：3.1。

### Task 3.5 — Timeline storage

**Files**：`observability/timeline.py`、MetricEvent model。  
**Acceptance Criteria**：每个 Job 状态变化写 Timeline Event。  
**Tests**：timeline sequence test。  
**Dependencies**：1.8、3.2。

## Phase 4

### Task 4.1 — Redis polling schedule

**Files**：`workers/scheduler.py`。  
**Acceptance Criteria**：到期 Creator 只被一个 Scheduler 取走。  
**Tests**：two-scheduler race test。  
**Dependencies**：3.1。

### Task 4.2 — AdaptivePollingPolicy

**Files**：`domain/scoring.py` 或 `services/monitor_service.py`。  
**Acceptance Criteria**：normal/warm/hot、backoff、rate pressure、jitter 全覆盖。  
**Tests**：table-driven unit tests。  
**Dependencies**：4.1。

### Task 4.3 — Platform rate limiter

**Files**：`services/monitor_service.py`、Redis token bucket helper。  
**Acceptance Criteria**：超过配额任务延后，不换号规避。  
**Tests**：rate limit tests。  
**Dependencies**：4.1。

### Task 4.4 — Monitor actor

**Files**：`workers/monitor_actors.py`。  
**Acceptance Criteria**：调用 Adapter，插入新 Post，写 Outbox。  
**Tests**：Mock integration test。  
**Dependencies**：2.7、3.3、4.2。

### Task 4.5 — Post dedup and lock

**Files**：Monitor Service。  
**Acceptance Criteria**：重复 Poll / Webhook 不创建重复 Post。  
**Tests**：concurrency test。  
**Dependencies**：4.4。

### Task 4.6 — Creator CRUD and monitor APIs

**Files**：`api/v1/creators.py`、Service、Schemas。  
**Acceptance Criteria**：创建、暂停、poll-now 完成。  
**Tests**：API integration。  
**Dependencies**：4.4。

## Phase 5

### Task 5.1 — Content normalization

**Files**：`services/content_service.py`。  
**Acceptance Criteria**：Mock Post 转统一 PostContent。  
**Tests**：normalization fixtures。  
**Dependencies**：4.4。

### Task 5.2 — Prompt loader and manifest

**Files**：`prompts/manifest.yaml`、Prompt Loader。  
**Acceptance Criteria**：按名称和版本加载；Hash 持久化。  
**Tests**：missing prompt and version tests。  
**Dependencies**：0.3。

### Task 5.3 — LLM provider interface and Mock provider

**Files**：`agents/provider.py`、`structured_output.py`。  
**Acceptance Criteria**：Mock Provider 可固定返回 Structured Output。  
**Tests**：contract tests。  
**Dependencies**：5.2。

### Task 5.4 — Concrete Anchor Extractor

**Files**：`agents/anchor_extractor.py`、Prompt。  
**Acceptance Criteria**：每条候选 Post 产生 1–5 Anchor 或明确低置信。  
**Tests**：caption fixtures。  
**Dependencies**：5.1、5.3。

### Task 5.5 — Opportunity scoring rules

**Files**：`domain/scoring.py`、`services/opportunity_service.py`。  
**Acceptance Criteria**：公式和 relationship multiplier 正确。  
**Tests**：exact numeric unit tests。  
**Dependencies**：5.4。

### Task 5.6 — Opportunity Agent

**Files**：`agents/opportunity_agent.py`、Prompt。  
**Acceptance Criteria**：Structured Output；Hard Rule 可覆盖模型。  
**Tests**：model output validation。  
**Dependencies**：5.3、5.5。

### Task 5.7 — Pipeline actor through opportunity decision

**Files**：`workers/pipeline_actors.py`。  
**Acceptance Criteria**：Post 可进入 SKIPPED 或 GENERATING。  
**Tests**：integration state transition tests。  
**Dependencies**：5.6、3.5。

## Phase 6

### Task 6.1 — Brand, Product, Campaign CRUD

**Files**：API routers/services/repositories。  
**Acceptance Criteria**：可配置 Approved/Forbidden Claims。  
**Tests**：API tests。  
**Dependencies**：1.4。

### Task 6.2 — Identity Profile APIs

**Files**：Account API and Service。  
**Acceptance Criteria**：品牌官方账号不能开启消费者身份。  
**Tests**：validation tests。  
**Dependencies**：1.5。

### Task 6.3 — Voice Profile APIs

**Files**：Voice Service、Schemas。  
**Acceptance Criteria**：版本化、启用/停用、批准示例可保存。  
**Tests**：version tests。  
**Dependencies**：1.5。

### Task 6.4 — Comment prompts

**Files**：`comment_fast_v1.md`、`comment_normal_v1.md`、`comment_partner_v1.md`。  
**Acceptance Criteria**：Prompt 明确禁止虚假体验、虚构身份、错别字伪装和 Detector 优化。  
**Tests**：prompt policy snapshot test。  
**Dependencies**：5.2、6.2、6.3。

### Task 6.5 — Comment Agent

**Files**：`agents/comment_agent.py`、Schemas。  
**Acceptance Criteria**：一次调用返回 2 个合法候选，记录 anchors/claims/version。  
**Tests**：structured output tests。  
**Dependencies**：6.4、5.3。

### Task 6.6 — Comment normalization and recent-history query

**Files**：`services/comment_service.py`、Repository。  
**Acceptance Criteria**：获取 account/campaign/creator 三个维度历史。  
**Tests**：query tests。  
**Dependencies**：1.7。

### Task 6.7 — Similarity engine

**Files**：`agents/quality_evaluator.py`。  
**Acceptance Criteria**：exact、3-gram、2-gram、prefix signature 可计算。  
**Tests**：known similarity fixtures。  
**Dependencies**：6.6。

### Task 6.8 — Authenticity and quality rules

**Files**：`quality_evaluator.py`、`quality_service.py`。  
**Acceptance Criteria**：generic、fake experience、fake identity、unsupported claim 可检测。  
**Tests**：E2E-004/005/006/007 对应 Unit/Integration。  
**Dependencies**：6.5、6.7。

### Task 6.9 — Comment generation pipeline

**Files**：Pipeline Actor。  
**Acceptance Criteria**：GENERATING → QUALITY_CHECKING → RISK_CHECKING/REVIEW/BLOCK。  
**Tests**：state integration。  
**Dependencies**：6.8、1.8。

## Phase 7

### Task 7.1 — RuleRiskEngine

**Files**：`services/risk_service.py`。  
**Acceptance Criteria**：Hard Rules 优先、可解释。  
**Tests**：table-driven rules。  
**Dependencies**：6.8。

### Task 7.2 — LLMRiskAgent

**Files**：`agents/risk_agent.py`、Prompt。  
**Acceptance Criteria**：只在 Rule 未决时调用；输出 ALLOW/REVIEW/BLOCK。  
**Tests**：provider fixtures。  
**Dependencies**：5.3、7.1。

### Task 7.3 — Risk orchestration

**Files**：Risk Service。  
**Acceptance Criteria**：Final Decision 持久化；Fail Closed。  
**Tests**：Risk Agent outage test。  
**Dependencies**：7.2。

### Task 7.4 — Review Job model/service

**Files**：Review Service/API。  
**Acceptance Criteria**：claim、approve、edit-and-approve、reject。  
**Tests**：concurrent claim test。  
**Dependencies**：7.3。

### Task 7.5 — Provenance and disclosure workflow

**Files**：Comment/Review Service。  
**Acceptance Criteria**：人工编辑更新 provenance；required-pending 阻止自动发布。  
**Tests**：E2E-010。  
**Dependencies**：7.4。

## Phase 8

### Task 8.1 — Publish idempotency

**Files**：`services/publish_service.py`、Repository。  
**Acceptance Criteria**：同 key 只创建一个 Job。  
**Tests**：concurrent create test。  
**Dependencies**：1.7。

### Task 8.2 — Publish Router

**Files**：Publish Service。  
**Acceptance Criteria**：根据 Capability 返回 Official/Manual/Unsupported。  
**Tests**：all capability states。  
**Dependencies**：2.2、8.1。

### Task 8.3 — Mock Publish Actor

**Files**：`workers/publish_actors.py`。  
**Acceptance Criteria**：Mock 评论发布并保存 receipt/rank。  
**Tests**：E2E-001/002/003。  
**Dependencies**：2.7、8.2。

### Task 8.4 — Publish uncertain and reconciliation

**Files**：Publish Actor/Service。  
**Acceptance Criteria**：success-but-timeout 不产生重复。  
**Tests**：E2E-009。  
**Dependencies**：8.3、2.6。

### Task 8.5 — Manual Publish API

**Files**：Comments/Review API。  
**Acceptance Criteria**：生成 Manual Job；运营可确认 published/skipped。  
**Tests**：API tests。  
**Dependencies**：8.2。

### Task 8.6 — Kill switches and limits

**Files**：System/Account/Campaign Service。  
**Acceptance Criteria**：平台、账号、Campaign 三层开关均在外部调用前生效。  
**Tests**：E2E-011。  
**Dependencies**：8.2。

## Phase 9

### Task 9.1 — RunMode routing

**Files**：Pipeline Service。  
**Acceptance Criteria**：NORMAL/FAST/FIRST_COMMENT/TOP5 配置生效。  
**Tests**：mode matrix。  
**Dependencies**：5.7、6.9。

### Task 9.2 — Fast path timeout budget

**Files**：Agent Provider and Pipeline。  
**Acceptance Criteria**：各 Stage 独立 timeout；无 generic fallback。  
**Tests**：timeout injection。  
**Dependencies**：9.1。

### Task 9.3 — Latency instrumentation

**Files**：`observability/timeline.py`、Metrics。  
**Acceptance Criteria**：所有必需时间戳和 latency 可查询。  
**Tests**：timeline metric test。  
**Dependencies**：3.5、9.2。

### Task 9.4 — Rank analytics

**Files**：Metrics Service。  
**Acceptance Criteria**：First/Top5 和 Coverage 分开计算。  
**Tests**：unknown samples not counted as failures。  
**Dependencies**：8.3、9.3。

### Task 9.5 — Performance benchmark

**Files**：`scripts/run_e2e_demo.py`、benchmark test。  
**Acceptance Criteria**：Mock FAST Path P95 达到本规范目标或生成明确报告。  
**Tests**：100 Post load test。  
**Dependencies**：9.4。

## Phase 10

### Task 10.1 — Frontend API client and auth

**Files**：`frontend/lib/api.ts`、Auth UI。  
**Acceptance Criteria**：登录和 token refresh 运行。  
**Tests**：Playwright login。  
**Dependencies**：0.4、Auth API。

### Task 10.2 — SSE endpoint

**Files**：`api/v1/events.py`。  
**Acceptance Criteria**：支持 heartbeat、filter、reconnect。  
**Tests**：SSE integration。  
**Dependencies**：3.5。

### Task 10.3 — Live page

**Files**：`frontend/app/live/page.tsx`。  
**Acceptance Criteria**：实时显示完整 Timeline。  
**Tests**：Playwright live flow。  
**Dependencies**：10.2。

### Task 10.4 — Review page

**Files**：Review UI。  
**Acceptance Criteria**：候选、锚点、质量、风险、身份、披露完整展示。  
**Tests**：approve/edit/reject E2E。  
**Dependencies**：7.4、10.1。

### Task 10.5 — Creator and Campaign pages

**Files**：对应页面。  
**Acceptance Criteria**：CRUD 和 monitor control。  
**Tests**：Playwright CRUD。  
**Dependencies**：4.6、6.1。

### Task 10.6 — Capabilities and Accounts pages

**Files**：Accounts/Settings UI。  
**Acceptance Criteria**：Capability、Identity、Auth、Kill Switch 可见。  
**Tests**：Playwright。  
**Dependencies**：6.2、8.6。

### Task 10.7 — Analytics page

**Files**：Analytics UI。  
**Acceptance Criteria**：Latency、Quality、Risk、First/Top5 Coverage。  
**Tests**：fixture visual test。  
**Dependencies**：9.4。

## Phase 11

### Task 11.1 — Encryption and secret handling

**Files**：`core/encryption.py`、Account Service。  
**Acceptance Criteria**：Token round-trip；日志无明文。  
**Tests**：encryption and log-redaction tests。  
**Dependencies**：1.5。

### Task 11.2 — RBAC

**Files**：Auth dependencies。  
**Acceptance Criteria**：角色权限与第 30 节一致。  
**Tests**：role matrix API tests。  
**Dependencies**：10.1。

### Task 11.3 — Audit logs

**Files**：`models/audit.py`、Audit Service。  
**Acceptance Criteria**：关键动作均写审计。  
**Tests**：review/publish/kill-switch audit tests。  
**Dependencies**：11.2。

### Task 11.4 — Circuit breaker and DLQ

**Files**：Worker Middleware、Health Service。  
**Acceptance Criteria**：连续失败打开 Circuit；任务进入 DLQ。  
**Tests**：failure injection。  
**Dependencies**：2.6、8.4。

### Task 11.5 — Observability dashboard APIs

**Files**：System/Metrics API。  
**Acceptance Criteria**：Queue、Worker、Polling、LLM、Publish 指标可用。  
**Tests**：metrics endpoint tests。  
**Dependencies**：9.3、11.4。

### Task 11.6 — Full DoD E2E

**Files**：`tests/e2e/test_full_demo.py`、`scripts/run_e2e_demo.py`。  
**Acceptance Criteria**：从 Brand 创建到 rank 展示全自动 PASS。  
**Tests**：`make test-e2e`。  
**Dependencies**：Phase 0–11 其他任务。

## Phase 12

### Task 12.1 — Real Adapter capability template

**Files**：各平台 `CAPABILITIES.md`。  
**Acceptance Criteria**：每项能力有状态、来源、日期、Scope、限制。  
**Tests**：documentation schema check。  
**Dependencies**：0.2、2.1。

### Task 12.2 — Douyin client skeleton

**Files**：`platforms/douyin/client.py`、`adapter.py`。  
**Implementation**：只实现经官方文档确认且具备授权的 read/reply 接口；顶级第三方评论保持 UNKNOWN。  
**Acceptance Criteria**：未授权时明确报错；无浏览器 fallback。  
**Tests**：mocked official API contract tests。  
**Dependencies**：12.1、2.1。

### Task 12.3 — Xiaohongshu adapter skeleton

**Files**：对应 Adapter 和 Capability 文档。  
**Acceptance Criteria**：未知社交能力抛 Unknown/Unsupported；不编造接口。  
**Tests**：contract tests。  
**Dependencies**：12.1。

### Task 12.4 — WeChat Channels adapter skeleton

**Files**：对应 Adapter 和 Capability 文档。  
**Acceptance Criteria**：同上。  
**Tests**：contract tests。  
**Dependencies**：12.1。

### Task 12.5 — Capability verification script

**Files**：`scripts/verify_capabilities.py`。  
**Acceptance Criteria**：输出 Matrix 和过期能力；不自动升级 UNKNOWN 为 SUPPORTED。  
**Tests**：fixture test。  
**Dependencies**：12.2–12.4。

---

# 35. Acceptance Tests

## 35.1 Repository Acceptance

```bash
make lint
make typecheck
make test
npm --prefix frontend run build
```

全部退出码为 0。

## 35.2 Local Runtime Acceptance

```bash
docker compose up --build
```

必须满足：

1. API health 200。
2. Frontend 可访问。
3. Worker heartbeat 正常。
4. Scheduler 正常。
5. PostgreSQL 和 Redis readiness 正常。

## 35.3 Product Acceptance

1. 创建 Brand A。
2. 创建 Brand Official Account 和真实 Identity Profile。
3. 创建 Voice Profile。
4. 创建 Campaign。
5. 创建目标 Creator。
6. 启动监控。
7. Mock Creator 发布羊绒穿搭 Post。
8. Monitor 检测到 Post。
9. 系统提取至少一个具体 Anchor。
10. Opportunity Score 达到阈值。
11. Comment Agent 生成两个非模板候选。
12. Quality Evaluator 验证上下文、真实性和去重。
13. Risk Engine 允许或转 Review。
14. Publish Router 发布至 Mock Platform。
15. UI 显示完整 Timeline。
16. 系统计算 Rank。
17. Analytics 显示 First/Top5 和 Coverage。
18. 审计日志记录生成来源和审批信息。

## 35.4 Safety Acceptance

必须通过以下测试：

- 任何包含 fake purchase experience 的自动候选不得发布。
- 品牌号不得以普通消费者身份发言。
- Capability UNKNOWN 不得调用外部发布 API。
- AI disclosure pending 不得自动发布。
- 项目中不存在 detector-evasion 评分、Prompt 或接口。
- 项目中不存在 CAPTCHA、设备指纹、浏览器模拟发布模块。

---

# 36. Definition of Done

MVP 完成需要同时满足：

```text
[ ] docker compose 一键启动
[ ] Mock Platform 完整运行
[ ] Creator Monitor 可发现新 Post
[ ] Dynamic Polling 可测试
[ ] Fast/Slow Path 可切换
[ ] Concrete Anchors 可生成
[ ] Opportunity Score 可解释
[ ] Comment Agent Structured Output
[ ] Account Identity 约束生效
[ ] Brand Voice 生效
[ ] Quality Evaluator 生效
[ ] Fake Experience / Fake Identity 被阻止
[ ] Duplicate Detection 生效
[ ] Risk Engine 生效
[ ] Review UI 可用
[ ] Publish Router 不调用未支持能力
[ ] Mock Publish 幂等
[ ] Publish Uncertain 可 Reconcile
[ ] SSE Live Timeline 可用
[ ] First / Top5 + Coverage 可用
[ ] Token 加密和 RBAC 可用
[ ] Audit Log 可用
[ ] 完整 E2E 自动测试 PASS
[ ] NON_GOALS 和 Capability 文档齐全
```

---

# 37. Implementation Order

精确执行顺序见同目录：

```text
IMPLEMENTATION_ORDER.md
```

Codex / Claude Code 必须逐项执行，不得跳过前置依赖，也不得在真实平台 Adapter 前实现未验证的自动发布路径。

---

# 38. Policy and Research Notes

工程设计必须持续遵守以下底线：

1. 平台对垃圾信息、过度营销、无关评论和规避技术审核通常有明确限制。
2. 未经许可的自动化程序、假冒注册、批量注册和不正当数据获取不得作为产品路径。
3. 中国现行 AI 生成合成内容标识规则覆盖文本等内容，并要求在适用场景下声明和使用平台标识功能；不得恶意删除、篡改、伪造或隐藏相关标识。
4. 因短评论、人工编辑、平台能力和具体业务场景可能存在适用差异，最终披露策略须由平台规则和法务确认；系统必须保留支持能力，不能默认隐匿。
5. 所有真实平台能力都应记录证据来源、验证日期、Scope 和失效时间。

