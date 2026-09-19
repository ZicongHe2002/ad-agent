# FirstComment Agent — Consolidated Engineering Specification

This document is the consolidated English edition of the project's four normative
specifications. It preserves requirement identifiers, code, schemas, API paths,
state names, checklists, and capability statuses exactly as defined by the source
documents.

## Contents

1. Product and Engineering Specification
2. Implementation Order
3. Non-Goals and Production Safety Boundaries
4. Platform Capability Matrix

---

# Part I — Product and Engineering Specification

# FirstComment Agent

## Implementation-Ready Engineering Specification

**Version**: v1.0  
**Baseline date**: 2026-09-02  
**Target audience**: Claude Code / Codex / Cursor / Windsurf, and the engineering leads responsible for acceptance  
**Deliverable**: A locally runnable Modular Monolith + complete Mock Platform + pluggable real-platform Adapter skeletons

---

## 0. Requirements Clarification and Safety Boundaries

The real business problems this project must solve are:

1. Comments must read as if written by someone who carefully read the content, rather than as a uniform template.
2. Account communications must be consistent, natural, and aligned with the identity of the real brand or disclosed operator.
3. Comments must be contextually relevant, linguistically diverse, and adapted to the platform.
4. The system must reduce the risks of spam, duplicate comments, fabricated experiences, and excessive marketing.

The project **does not implement**:

- Defeating, evading, or deceiving platform AI detection, content moderation, or anti-spam systems.
- Disguising brand, bot, or bulk-operated accounts as ordinary human consumers.
- Generating fabricated purchases, occupations, ages, genders, life experiences, or social relationships.
- Simulating humans through typo injection, random pauses, device-behavior simulation, account farming, fingerprint spoofing, or similar techniques.
- Removing, altering, hiding, or falsifying AI-content labels, platform provenance labels, or audit information.
- Using an “AI detection pass rate” as a training, generation, A/B testing, or release acceptance metric.

In engineering terms, “human-like” is implemented as:

> **Natural, Specific, Context-Grounded, Truthful and Account-Consistent**

That is: natural, specific, grounded in post context, truthful, non-impersonating, and consistent with the account's real identity.

---

# 1. Project Overview

## 1.1 Project Name

Canonical project name:

```text
FirstComment Agent
```

Repository name:

```text
firstcomment-agent
```

## 1.2 Project Objective

The system continuously monitors a set of target Creators, subject to platform capabilities:

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

The system aims to reduce end-to-end latency from a Creator publishing content to a comment entering the publishing workflow, and measures Chronological First Comment / Top5 when observable.

## 1.3 Core Product Principles

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

## 1.4 Initial Product Form

The MVP is a complete, runnable system providing:

```text
Real-time content-opportunity discovery
+ AI comment suggestions
+ Authenticity and quality checks
+ Independent risk checks
+ Human review
+ Mock automatic publishing
+ Official-capability adapter skeletons for real platforms
+ Latency and ranking analytics
```

If a real platform has no confirmed top-level comment publishing capability, the workflow enters:

```text
WAITING_MANUAL_PUBLISH
```

It must not invoke simulated clicks, non-public endpoints, or fabricated APIs.

---

# 2. Goals

## G-001 Low-Latency Discovery

- Configure priorities and dynamic polling for Creators.
- Support event-driven operation for the Mock Platform.
- For real platforms, use only verified official Webhooks, Search APIs, Polling APIs, or Partner Capabilities.

## G-002 Contextually Relevant Comments

- Every comment must anchor to at least one specific element in the post.
- Do not generate content-free comments such as “looks great,” “nice,” or “showing support.”
- FAST mode must still include a post anchor.

## G-003 Non-Templated Without Impersonation

- Achieve diversity through post anchors, authentic Brand Voice, sentence-pattern libraries, and deduplication against recent comments.
- Do not create “naturalness” through typos, random grammatical errors, fabricated first-person experiences, or simulated human behavior.

## G-004 Authentic Account Identity

- Every publishing account must be bound to a real subject type.
- Brand accounts must not impersonate ordinary consumers.
- Employee or partner accounts require explicit authorization and a disclosure policy.

## G-005 Safe Publishing

- Before publishing, run Capability, Identity, Quality, Risk, and Dedup Checks.
- Automatic publishing is prohibited if any critical check fails.

## G-006 Testability

- The Mock Platform fully supports Creators, Posts, Comments, ranking, latency, errors, and rate limiting.
- All critical workflows have Unit, Integration, and E2E tests.

## G-007 Observability

- Record Detection, Fetch, Analysis, Generation, Quality, Risk, Review, Publish, and E2E latency from day one.
- Display `UNKNOWN` for unobservable real-platform rankings.

---

# 3. Non-Goals

See `NON_GOALS.md` in the repository root.

The MVP explicitly excludes:

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

As a Brand Manager, I can create brands, products, Campaigns, brand voices, and prohibited claims, and know which brand facts each comment references.

## US-002 Operator

As an Operator, I can add Creators, view new content, select candidate comments, edit and publish them, or skip risky content.

## US-003 Reviewer

As a Reviewer, I can see the post summary, concrete anchors, account identity, candidate comments, duplication level, authenticity risk, commercial risk, and platform capabilities.

## US-004 Admin

As an Admin, I can view platform capability status, Token status, queues, Workers, failed jobs, and the global Kill Switch.

## US-005 Engineer

As an Engineer, I can run the complete workflow using only the Mock Platform, without any real-platform permissions.

## US-006 Compliance Reviewer

As a Compliance Reviewer, I can trace whether a comment is Human Authored, AI Assisted, or AI Generated, and inspect human edits, approvers, and platform disclosure status.

---

# 5. Functional Requirements

## 5.1 Creators and Monitoring

| ID | Requirement |
| ---|---|
| FR-001 | Create, update, and deactivate Creators |
| FR-002 | A Creator may be linked to multiple platform accounts |
| FR-003 | Configure Creator Priority, Poll Interval, and expected publishing windows |
| FR-004 | Record last_checked_at, last_post_at, and last_external_post_id |
| FR-005 | Explicitly return `UNSUPPORTED` or `UNKNOWN` when the platform cannot be monitored |

## 5.2 Content Discovery and Processing

| ID | Requirement |
| ---|---|
| FR-010 | Deduplicate new Posts by `(platform, external_post_id)` |
| FR-011 | Store the original Payload Hash and normalized content |
| FR-012 | Support FAST / MEDIUM / SLOW analysis paths |
| FR-013 | Extract 1–5 Concrete Anchors for each Post |
| FR-014 | Calculate an Opportunity Score with explainable components |

## 5.3 Comment Generation

| ID | Requirement |
| ---|---|
| FR-020 | Return candidate comments using Structured Output |
| FR-021 | Each candidate contains at least one post anchor |
| FR-022 | Prohibit fabricated first-person experiences and identities |
| FR-023 | Candidate comments must not cite unapproved Product Claims |
| FR-024 | By default, one model call returns two candidates; human-review mode may return three |
| FR-025 | Store Prompts as files and record prompt_version |

## 5.4 Authenticity and Quality

| ID | Requirement |
| ---|---|
| FR-030 | Bind each Brand Account to an Account Identity Profile |
| FR-031 | Bind each account to a Brand Voice; do not create a fabricated “human Persona” |
| FR-032 | Calculate relevance, specificity, fluency, voice_match, and novelty |
| FR-033 | Run exact, normalized, and n-gram similarity checks against recent comments |
| FR-034 | Detect generic praise, fake experience, fake identity, and unsupported claims |
| FR-035 | Do not store or optimize `ai_detector_score` |
| FR-036 | Store Content Provenance and AI Disclosure Status |

## 5.5 Risk Control and Publishing

| ID | Requirement |
| ---|---|
| FR-040 | Run RuleRiskEngine before LLMRiskAgent |
| FR-041 | GENERAL_CREATOR + brand mention defaults to REVIEW |
| FR-042 | COMPETITOR defaults to BLOCK / SKIP |
| FR-043 | Enter MANUAL or UNSUPPORTED when the Capability is not supported |
| FR-044 | Publishing jobs must have an idempotency_key |
| FR-045 | Publishing timeouts enter `PUBLISH_UNCERTAIN`; Reconcile before retrying |
| FR-046 | Support Kill Switches per platform, account, and Campaign |

## 5.6 Analytics

| ID | Requirement |
| ---|---|
| FR-050 | The Mock Platform calculates chronological_rank |
| FR-051 | Record `UNKNOWN` when a real platform is not observable |
| FR-052 | Record Human Acceptance Rate and Edit Rate |
| FR-053 | Record Comment Removal / Rejection outcomes when capabilities permit |
| FR-054 | Do not use AI Detector Pass Rate as a metric |

---

# 6. Non-Functional Requirements

## 6.1 Latency Targets

The following are system targets, not platform guarantees.

| Stage | FAST P50 | FAST P95 |
| ---|---:|---:|
| Detection | 2s | 10s |
| Fetch | 300ms | 1.5s |
| Fast Analysis | 150ms | 600ms |
| Generation | 500ms | 1.8s |
| Quality + Rule Risk | 80ms | 300ms |
| LLM Risk (when needed) | 400ms | 1.5s |
| Official Publish | 700ms | 3s |
| AI Ready E2E | 4s | 15s |

Human-assisted path:

| Stage | P50 | P95 |
| ---|---:|---:|
| Review Queue Wait | 10s | 60s |
| Human Decision | 10s | 60s |
| Manual Publish | 10s | 90s |

## 6.2 Reliability

- ACK the Queue only after critical DB writes succeed.
- Critical jobs use at-least-once delivery; the business layer achieves effectively-once behavior through idempotency.
- Worker restarts must not produce duplicate comments.
- A failure on one platform must not block other platforms.

## 6.3 Security

- Store Tokens encrypted.
- Secrets must never appear in logs, plaintext database fields, frontend Bundles, or Git.
- Implement RBAC and audit logs starting with the MVP.

## 6.4 Policy Safety

- Disable Auto Publish when the Policy Version expires.
- A Capability cannot be marked `SUPPORTED` until verified.
- Retain internal records of AI content provenance and disclosure status.

## 6.5 Maintainability

- Python type checking passes.
- Core-module coverage target ≥ 80%.
- Adapter contract tests cover all Capability states.

---

# 7. Architecture

## 7.1 Architecture Style

```text
Modular Monolith
+ Multiple Worker Processes
+ PostgreSQL Source of Truth
+ Redis Broker / Cache / Schedule
+ Adapter-based External Integrations
```

Do not introduce Kubernetes, Kafka, a Service Mesh, or multi-repository microservices in the MVP.

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

## 8.1 Directory Responsibilities

- `domain/`: enums, capability models, state machines, and scoring formulas, with no network or database side effects.
- `models/`: SQLAlchemy ORM.
- `schemas/`: Pydantic models for APIs and Agent Structured Output.
- `services/`: business orchestration and transaction boundaries.
- `agents/`: model Providers, Prompts, structured output, and quality evaluation.
- `platforms/`: platform capabilities and external calls.
- `workers/`: Dramatiq Actors, Scheduler, and Outbox Relay.
- `observability/`: logs, Metrics, and Timeline.
- `tests/contract/`: Adapter and Agent Provider contract tests.

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

Selection:

```text
Dramatiq + Redis Broker + AsyncIO Middleware
```

Reasons:

- Compared with a custom Queue, it provides mature Actor, Retry, and Middleware mechanisms.
- Compared with full Celery, it requires less MVP configuration.
- Supports `async def` Actors, suitable for I/O-intensive work such as platform APIs and LLMs.
- ARQ is currently in maintenance-only mode, so it is not the default dependency for a new project.

## 9.3 Storage

```text
PostgreSQL 16+
Redis 7+
S3-compatible Object Storage (the MVP may use local MinIO)
```

The MVP does not introduce a separate vector database; comment deduplication uses PostgreSQL + rules, with pgvector added later if needed.

## 9.4 Frontend

```text
Next.js
TypeScript
React
Tailwind CSS
```

## 9.5 Realtime UI

Selection:

```text
Server-Sent Events (SSE)
```

Rationale: Live Timeline is primarily one-way server push, so SSE is simpler than WebSocket; review actions continue to use ordinary REST.

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

Rules:

- `BRAND_OFFICIAL.may_speak_as_consumer` must be false.
- `may_use_first_person_experience=true` is allowed only with an auditable human author, a genuine experience, and human confirmation.
- Automated paths must not generate first-person purchase or usage experiences.

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

VoiceProfile is a brand communication standard, not a fabricated persona.

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

Note: The Schema **must not contain** `ai_detector_score`, `human_probability`, or `bot_evasion_score`.

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

## 11.1 Critical Unique Constraints

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

For the MVP, `intent_key` is fixed as:

```text
TOP_LEVEL_PRIMARY
```

By default, one account may publish only one top-level comment for the same Post and Campaign.

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

Creating a Post and its `post.detected` Outbox Event must occur in one database transaction.

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

Audit the following actions:

- Brand Voice changes
- Identity Profile changes
- Campaign activation/pausing
- Capability status changes
- Auto Publish toggles
- Review decisions
- Comment edits
- Publish requests and results
- AI Disclosure status changes

## 11.5 Migration Rules

- All Migrations can be applied forward and rolled back in test environments.
- Do not drop production columns without safeguards in the same Migration.
- Put Enum changes in a separate Migration.
- CI upgrades an empty database to head on every run.

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

- `UNKNOWN` is not equivalent to `SUPPORTED`.
- `comment_reply` must not be used as `top_level_comment`.
- Adapters must not internally fall back to browser automation.
- External requests must have a timeout, trace_id, and structured logs.
- Every real Adapter must have a `CAPABILITIES.md`.

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

Real capabilities are governed by `PLATFORM_CAPABILITIES.md` and each Adapter's `CAPABILITIES.md`.

---

# 13. Mock Platform

## 13.1 Purpose

The Mock Platform is the first platform that must be fully implemented, enabling validation of the entire product without real-platform permissions.

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
| ---|---|---|
| POST | `/api/v1/mock/creators` | Create Creator |
| POST | `/api/v1/mock/posts` | Creator publishes a new Post |
| GET | `/api/v1/mock/posts/{post_id}` | Read Post |
| POST | `/api/v1/mock/posts/{post_id}/comments` | Publish Comment |
| POST | `/api/v1/mock/posts/{post_id}/simulate-comments` | Simulate comments from other users |
| GET | `/api/v1/mock/posts/{post_id}/comments` | Read comment list |
| POST | `/api/v1/mock/failure-profile` | Configure failure injection |
| POST | `/api/v1/mock/capabilities` | Change capability status |
| POST | `/api/v1/mock/reset` | Clear Mock data |

## 13.4 Comment Ranking

Chronological Rank:

```python
def chronological_rank(comments: list[MockComment], comment_id: UUID) -> int:
    ordered = sorted(comments, key=lambda x: (x.created_at, str(x.id)))
    return next(i for i, item in enumerate(ordered, start=1) if item.id == comment_id)
```

Visible Rank simulation strategies:

```text
CHRONOLOGICAL
LIKES_WEIGHTED
AUTHOR_PINNED
PERSONALIZED_RANDOM_SEEDED
```

Mock random ordering must use a fixed seed so tests are reproducible.

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

Use a Sorted Set:

```text
key: poll_schedule:{platform}
score: unix timestamp of next_poll_at
member: creator_platform_account_id
```

Every 500 ms, the Scheduler:

1. Atomically reads due members.
2. Removes them from the ZSET.
3. Sends them to the corresponding Queue.
4. After the Worker completes, recalculates and inserts the next run time.

Use a Lua Script or Redis Transaction to prevent multiple Schedulers from claiming the same job.

## 14.4 Lock

```text
poll_lock:{creator_platform_account_id}
TTL = max(expected_request_timeout * 2, 30s)
```

If the Lock is not acquired, ACK the job immediately without repeating the request.

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

Jitter prevents thundering herds; it is not used to imitate human behavior.

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

Any real-platform setting below 10 seconds requires explicit approval from the Capability Owner.

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

- The Relay fetches unpublished Events every 250 ms.
- Use `FOR UPDATE SKIP LOCKED`.
- Set `published_at` after successful Queue insertion.
- Repeated failures trigger an alert but do not delete the Event.

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

Enter FAST when the following conditions are met:

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

FAST does not wait for:

- Full video download
- Full ASR
- Large multimodal models
- Full historical comment retrieval

But it must wait for:

- Capability Check
- Identity Check
- Concrete Anchor
- Claim Check
- Duplicate Check
- Hard Risk Rules

## 17.4 Fallback

Enter SLOW in the following cases:

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

Timeout policy:

- Do not use fallback templates that have not been context-validated.
- When FIRST_COMMENT mode times out, route to Review/Skip instead of publishing a generic comment.

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
Existing Comments (if official capabilities permit)
```

## 18.2 Use Cases

- NORMAL mode
- FAST with low confidence
- High-value Partner Creator
- Product Claim requires confirmation
- An image or video is the primary semantic carrier

## 18.3 Processing Order

```text
OCR first
→ thumbnail vision
→ partial ASR
→ full ASR only if still uncertain
→ multimodal model last
```

## 18.4 Storage

- Store model-derived summaries; do not retain complete third-party videos permanently by default.
- Media Retention is governed by platform authorization and company policy.

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

Hard Rules always override scores.

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

The System Prompt must include:

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

- Do not mention the brand.
- Ground comments in specific anchors such as styling, color, cut, or setting.
- This is the default policy for GENERAL_CREATOR.

### EXPERT_COMMENT

- Provide truthful, verifiable material or styling knowledge.
- Do not use absolute, medicalized, or unsubstantiated claims.

### LIGHT_BRAND_MENTION

- Allowed only for Partners / Campaigns.
- Brand identity must be identifiable.
- Default to human review.

### PARTNER_BRAND_COMMENT

- Applies to formally partnered Creators.
- Comment text follows the Campaign disclosure template while remaining grounded in specific content.

### PRODUCT_RELATED

- Use Approved Claims only.
- Fabricated usage experiences are prohibited.

### CAMPAIGN_DISCLOSURE

- Clearly state the partnership or brand identity.
- Do not recommend products in the voice of an ordinary consumer.

## 20.5 Implementing “Naturalness”

Permitted quality techniques:

- Use specific post anchors.
- Use multiple approved sentence structures.
- Adapt to platform length, punctuation, and Emoji conventions.
- Adjust wording to the authentic Brand Voice.
- Check duplication and similarity against recent comments.
- Continuously improve Prompts using human edits and feedback.

Prohibited “naturalness” techniques:

- Deliberately adding typos, malformed sentences, or internet slang to deceive detection.
- Randomly simulating typing speed, online times, or human schedules.
- Creating a fabricated consumer Persona.
- Rewriting repeatedly based on an AI Detector score.
- Hiding AI-content provenance or platform-required labels.

## 20.6 Recent Comment Retrieval

The MVP retrieves the most recent:

```text
same brand_account: 100 comments
same campaign: 100 comments
same creator: 20 comments
```

This is used for duplication checks and to avoid repeatedly using the same opening.

---

# 21. Authenticity & Quality Evaluator

## 21.1 Purpose

This module makes comment quality reflect careful reading by a person; it does not disguise a machine as a person.

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

FIRST_COMMENT mode automatically Regenerates at most once; a second failure routes directly to Review/Skip.

## 21.5 Similarity MVP

```text
exact normalized match
character 3-gram Jaccard
word 2-gram Jaccard
same prefix signature
same CTA signature
```

Recommended thresholds:

```text
similarity >= 0.90 → BLOCK
0.82 <= similarity < 0.90 → REVIEW
```

These thresholds support anti-spam and content quality; they are not used to defeat platform detection.

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

Explicitly prohibited:

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
→ LLMRiskAgent (handles only semantically uncertain items)
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

Identity deception, fake experience, and capability bypass are always BLOCKed.

## 22.5 Fail Closed

Automatic publishing is prohibited under any of the following conditions:

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

If a network Timeout occurs but publishing may have succeeded:

```text
PUBLISHING
→ PUBLISH_UNCERTAIN
→ reconcile_publish
→ PUBLISHED or READY_FOR_RETRY
```

Do not retry directly.

## 23.5 Manual Publish Workflow

A Manual Job contains:

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

Default to Review:

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

Store:

```text
original_candidate_text
final_text
reviewer_id
edit_distance
edit_reason
resolved_at
```

After human editing, update Content Provenance to:

```text
AI_ASSISTED_HUMAN_EDITED
```

---

# 25. API Specification

All API prefixes:

```text
/api/v1
```

Standard error format:

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
| ---|---|---|---|---|
| POST | `/auth/login` | email, password | access_token, user | 200/401 |
| GET | `/auth/me` | bearer token | user | 200/401 |

## 25.2 Brands

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| POST | `/brands` | BrandCreate | BrandRead | 201/422 |
| GET | `/brands` | filters | Page[BrandRead] | 200 |
| GET | `/brands/{id}` | — | BrandRead | 200/404 |
| PATCH | `/brands/{id}` | BrandUpdate | BrandRead | 200/404 |

## 25.3 Products

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| POST | `/products` | ProductCreate | ProductRead | 201 |
| GET | `/products` | brand_id | Page | 200 |
| PATCH | `/products/{id}` | ProductUpdate | ProductRead | 200/404 |

## 25.4 Campaigns

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| POST | `/campaigns` | CampaignCreate | CampaignRead | 201 |
| POST | `/campaigns/{id}/activate` | — | CampaignRead | 200/409 |
| POST | `/campaigns/{id}/pause` | — | CampaignRead | 200 |
| GET | `/campaigns/{id}/metrics` | range | metrics | 200 |

## 25.5 Creators

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| POST | `/creators` | CreatorCreate | CreatorRead | 201 |
| GET | `/creators` | platform, relationship, state | Page | 200 |
| PATCH | `/creators/{id}` | CreatorUpdate | CreatorRead | 200 |
| POST | `/creators/{id}/monitor` | — | MonitorState | 200/409 |
| POST | `/creators/{id}/pause` | — | MonitorState | 200 |
| POST | `/creators/{id}/poll-now` | — | TaskReceipt | 202/429 |

## 25.6 Platform Accounts

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| POST | `/platform-accounts` | account + identity + voice | AccountRead | 201 |
| GET | `/platform-accounts` | platform | Page | 200 |
| POST | `/platform-accounts/{id}/verify-auth` | — | AuthStatus | 200/401 |
| POST | `/platform-accounts/{id}/kill-switch` | enabled | AccountRead | 200 |

## 25.7 Posts

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| GET | `/posts` | filters | Page[PostRead] | 200 |
| GET | `/posts/{id}` | — | PostDetail | 200/404 |
| POST | `/posts/{id}/reanalyze` | mode | TaskReceipt | 202/409 |
| GET | `/posts/{id}/timeline` | — | Timeline | 200 |

## 25.8 Comments

| Method | Path | Request | Response | Status |
| ---|---|---|---|---|
| GET | `/comments/candidates` | status | Page | 200 |
| GET | `/comments/published` | filters | Page | 200 |
| POST | `/comments/candidates/{id}/regenerate` | reason | CandidateBatch | 200/409 |
| POST | `/comments/{id}/reconcile` | — | PublishResult | 202 |

## 25.9 Review

See Section 24.

## 25.10 Metrics

| Method | Path | Purpose |
| ---|---|---|
| GET | `/metrics/overview` | Core KPIs |
| GET | `/metrics/latency` | P50/P90/P95/P99 |
| GET | `/metrics/quality` | Quality and human edits |
| GET | `/metrics/ranking` | First / Top5 + Coverage |

## 25.11 System

| Method | Path | Purpose |
| ---|---|---|
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

Supported parameters:

```text
creator_id
post_id
campaign_id
event_type
```

## 25.13 Mock

See Section 13.

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

Display in real time:

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

Must support:

```text
keyboard shortcut 1/2/3 select candidate
E edit
A approve
S skip
open post
copy comment
```

Keyboard shortcuts must not bypass confirmation rules.

## 26.4 Account Page

Display:

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

For each platform, display:

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

No Service may assign `job.state` directly.

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

Unobservable does not count as failure.

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
| ---|---:|---|
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

By `(platform, operation)` dimension:

```text
CLOSED
OPEN
HALF_OPEN
```

Trigger examples:

```text
5 consecutive platform failures
or 50% failure in rolling 20 requests
```

When OPEN, do not attempt concealed alternative paths.

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

Scheduled jobs check:

```text
PUBLISH_UNCERTAIN older than 30s
PUBLISHING older than timeout
WAITING_REVIEW expired
outbox unpublished older than 60s
```

---

# 30. Security

## 30.1 Authentication and RBAC

Roles:

```text
ADMIN
BRAND_MANAGER
REVIEWER
VIEWER
```

Permissions:

- Only ADMIN may modify Capabilities and Kill Switches.
- BRAND_MANAGER may modify Brands, Campaigns, and Voice.
- REVIEWER may review but may not modify platform Tokens.
- VIEWER is read-only.

## 30.2 Token Encryption

- Use AES-256-GCM.
- The Master Key comes from an environment variable or Secret Manager.
- Store `ciphertext + nonce + key_version` in the database.
- Logs never output Tokens.

## 30.3 Audit

The following actions must be recorded:

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

- Always record Comment Provenance internally.
- When a platform or law requires AI disclosure, the workflow must support and prompt for it.
- Provide no code path to remove, hide, or alter AI labels.
- If disclosure requirements are unclear, route to human review rather than hiding by default.

## 30.5 Privacy

- Do not build sensitive profiles of ordinary users.
- Do not store unnecessary personal information.
- Purge media and third-party content according to the Retention Policy.

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

For each Adapter:

```text
get_capabilities returns all fields
unsupported method raises UnsupportedCapabilityError
reply is not treated as top-level comment
timeout maps to PlatformTemporaryError or PublishUncertainError
no adapter invokes browser automation fallback
```

For each Agent Provider:

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
candidate says “I bought from our brand” as an ordinary consumer
Expected BLOCK
```

### E2E-006 Generic Comment Review

```text
candidate = “Looks great, showing support”
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

Grafana may be enabled as an optional Profile.

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

Readiness must check:

```text
PostgreSQL
Redis
Outbox Relay heartbeat
Critical Worker heartbeat
```

---

# 33. Development Phases

## Phase 0 — Governance and Bootstrap

Objective: establish safety boundaries, repository, toolchain, and runtime skeleton.

## Phase 1 — Core Domain and Database

Objective: implement enums, ORM, Migrations, Repositories, and state machines.

## Phase 2 — Mock Platform

Objective: implement a platform that can simulate Posts, Comments, rankings, and errors.

## Phase 3 — Queue, Scheduler and Event Pipeline

Objective: implement Dramatiq, Redis ZSET, Outbox, and Timeline.

## Phase 4 — Creator Monitor

Objective: implement dynamic Polling, deduplication, and new-Post detection.

## Phase 5 — Content and Opportunity Pipeline

Objective: normalize content, extract anchors, score opportunities, and route paths.

## Phase 6 — Comment and Quality Layer

Objective: implement Structured Generation, Brand Voice, identity consistency, and non-templated quality checks.

## Phase 7 — Risk and Review

Objective: implement Rule Risk, LLM Risk, and human review.

## Phase 8 — Publishing and Idempotency

Objective: implement the Router, Mock Publish, Manual Workflow, and Reconciliation.

## Phase 9 — Fast Path and Latency

Objective: optimize the First Comment path and add complete latency metrics.

## Phase 10 — Frontend and SSE

Objective: implement the Live, Review, Capabilities, and Analytics pages.

## Phase 11 — Reliability, Security and E2E

Objective: implement error injection, Circuit Breaker, encryption, auditing, and DoD E2E.

## Phase 12 — Real Platform Adapter Skeletons

Objective: establish strict capability documentation and official API Adapter skeletons without implementing unverified capabilities.

---

# 34. Detailed Tasks

Each item below is designed to be completed independently within 30 minutes to several hours.

## Phase 0

### Task 0.1 — Create repository skeleton

**Objective**: Create the root directory, backend, frontend, docs, and scripts.  
**Files to Create**: Base files in the root directory tree.  
**Implementation**: Create empty packages, README, Makefile, and `.gitignore`.  
**Acceptance Criteria**: Directory structure matches this specification; Git working tree is clean.  
**Tests**: Manually inspect `find . -maxdepth 3 -type f`.  
**Dependencies**: None.

### Task 0.2 — Add NON_GOALS and capability policy

**Objective**: Record the prohibitions on detection evasion, human impersonation, and unofficial automation in the repository.  
**Files**:`NON_GOALS.md`, `PLATFORM_CAPABILITIES.md`.  
**Implementation**: Copy the boundaries and Capability status model from this specification.  
**Acceptance Criteria**: Documentation explicitly prohibits detector evasion, fake personas, and label removal.  
**Tests**:Documentation review checklist.  
**Dependencies**:0.1.

### Task 0.3 — Backend tooling

**Objective**: Configure the Python project.  
**Files**:`backend/pyproject.toml`.  
**Implementation**:FastAPI, SQLAlchemy, Alembic, Pydantic, Dramatiq, Redis, httpx, pytest, Ruff, mypy.  
**Acceptance Criteria**: `ruff check .` and `mypy app` run successfully.  
**Tests**:`make lint && make typecheck`.  
**Dependencies**:0.1.

### Task 0.4 — Frontend tooling

**Objective**: Initialize a strict TypeScript Next.js project.  
**Files**:`frontend/*`.  
**Acceptance Criteria**: `npm run build` succeeds.  
**Tests**:`npm run lint`.  
**Dependencies**:0.1.

### Task 0.5 — Docker Compose baseline

**Objective**: Start PostgreSQL, Redis, API, and Frontend.  
**Files**:`docker-compose.yml`, `.env.example`.  
**Acceptance Criteria**: The health endpoint returns 200 after `docker compose up`.  
**Tests**:curl health.  
**Dependencies**:0.3, 0.4.

## Phase 1

### Task 1.1 — Core config and logging

**Files**:`core/config.py`, `core/logging.py`, `main.py`.  
**Implementation**:Pydantic Settings, JSON logs, trace_id middleware.  
**Acceptance Criteria**: Every request log includes a trace_id.  
**Tests**:`tests/unit/core/test_config.py`, API log integration test.  
**Dependencies**:0.3.

### Task 1.2 — Database session and Alembic

**Files**:`db/base.py`, `db/session.py`, `alembic.ini`, `migrations/env.py`.  
**Acceptance Criteria**: `alembic upgrade head` succeeds on an empty database.  
**Tests**:CI migration test.  
**Dependencies**:1.1.

### Task 1.3 — Implement enums and capabilities

**Files**:`domain/enums.py`, `domain/capabilities.py`.  
**Acceptance Criteria**: All Enums match this specification.  
**Tests**:serialization round-trip.  
**Dependencies**:0.3.

### Task 1.4 — Implement Brand, Product, Campaign models

**Files**: Corresponding `models/`, `schemas/`, and migration.  
**Acceptance Criteria**: CRUD schemas are valid; FKs and indexes exist.  
**Tests**:model and repository tests.  
**Dependencies**:1.2, 1.3.

### Task 1.5 — Implement Account, Identity and Voice models

**Files**:`account.py`, `identity_profile.py`, `voice_profile.py`.  
**Implementation**: Add a database Check Constraint preventing brand-official accounts from using an ordinary-consumer identity.  
**Acceptance Criteria**: Persisting an invalid combination fails.  
**Tests**:`test_identity_constraints.py`.  
**Dependencies**:1.4.

### Task 1.6 — Implement Creator and Post models

**Files**:`creator.py`, `post.py`, migration.  
**Acceptance Criteria**: `(platform, external_post_id)` is unique.  
**Tests**: Duplicate insertion raises IntegrityError.  
**Dependencies**:1.4.

### Task 1.7 — Implement Comment, Quality, Risk and Publish models

**Files**:`comment.py`, `risk.py`, `publish.py`.  
**Acceptance Criteria**: The Schema contains no detector-evasion fields; idempotency_key is unique.  
**Tests**:schema inspection test.  
**Dependencies**:1.5, 1.6.

### Task 1.8 — Implement state machine

**Files**:`domain/state_machine.py`.  
**Acceptance Criteria**: Invalid transitions raise `InvalidStateTransition`.  
**Tests**: Enumerate all valid and invalid transitions.  
**Dependencies**:1.3, 1.7.

### Task 1.9 — Generic repositories and transaction helpers

**Files**: `repositories/base.py` and core Repositories.  
**Acceptance Criteria**: A Service can write a Post + Outbox in one transaction.  
**Tests**:transaction rollback test.  
**Dependencies**:1.7.

## Phase 2

### Task 2.1 — Platform base contract

**Files**:`platforms/base.py`, `platforms/errors.py`.  
**Acceptance Criteria**: All methods and error mappings are defined.  
**Tests**:abstract contract test.  
**Dependencies**:1.3.

### Task 2.2 — Platform registry

**Files**:`platforms/registry.py`.  
**Acceptance Criteria**: Retrieve Adapters by Platform; unknown platforms fail.  
**Tests**:registry unit tests.  
**Dependencies**:2.1.

### Task 2.3 — Mock creator and post API

**Files**:`platforms/mock/service.py`, `api/v1/mock.py`.  
**Acceptance Criteria**: Creators and Posts can be created.  
**Tests**:API integration tests.  
**Dependencies**:2.2, 1.6.

### Task 2.4 — Mock comments and chronological ranking

**Files**:`platforms/mock/ranking.py`, Mock comment endpoints.  
**Acceptance Criteria**: Rankings are correct with 0/3/5 existing comments.  
**Tests**: Foundation tests for E2E-001/002/003.  
**Dependencies**:2.3.

### Task 2.5 — Mock visible ranking modes

**Files**:`ranking.py`.  
**Acceptance Criteria**: Four ranking modes are configurable and their seed is reproducible.  
**Tests**:snapshot tests.  
**Dependencies**:2.4.

### Task 2.6 — Failure injection

**Files**:`failure_injection.py`.  
**Acceptance Criteria**: Can simulate latency, 429, 500, timeout, and success-but-timeout.  
**Tests**:parameterized integration tests.  
**Dependencies**:2.3.

### Task 2.7 — MockPlatformAdapter

**Files**:`platforms/mock/adapter.py`.  
**Acceptance Criteria**: Fully implements the Adapter Contract.  
**Tests**: The contract suite passes completely.  
**Dependencies**:2.4, 2.6.

## Phase 3

### Task 3.1 — Dramatiq broker

**Files**:`workers/broker.py`, `workers/middleware.py`.  
**Acceptance Criteria**: A Worker can consume a test actor; async actors run successfully.  
**Tests**:broker integration test.  
**Dependencies**:0.5.

### Task 3.2 — Event schema

**Files**:`domain/events.py`.  
**Acceptance Criteria**: Event Envelopes are serializable and version is required.  
**Tests**:schema tests.  
**Dependencies**:1.3.

### Task 3.3 — Outbox model and relay

**Files**:`models/event.py`, `repositories/outbox.py`, `workers/outbox_relay.py`.  
**Acceptance Criteria**: Outbox publishes only once; failures can be retried.  
**Tests**:concurrent relay test.  
**Dependencies**:3.1, 3.2, 1.9.

### Task 3.4 — Redis priority queues

**Files**:broker queue config.  
**Acceptance Criteria**: critical/high/normal/low queues are consumed separately.  
**Tests**:priority ordering integration test.  
**Dependencies**:3.1.

### Task 3.5 — Timeline storage

**Files**:`observability/timeline.py`, MetricEvent model.  
**Acceptance Criteria**: Every Job state change writes a Timeline Event.  
**Tests**:timeline sequence test.  
**Dependencies**:1.8, 3.2.

## Phase 4

### Task 4.1 — Redis polling schedule

**Files**:`workers/scheduler.py`.  
**Acceptance Criteria**: A due Creator is claimed by only one Scheduler.  
**Tests**:two-scheduler race test.  
**Dependencies**:3.1.

### Task 4.2 — AdaptivePollingPolicy

**Files**: `domain/scoring.py` or `services/monitor_service.py`.  
**Acceptance Criteria**: normal/warm/hot, backoff, rate pressure, and jitter are fully covered.  
**Tests**:table-driven unit tests.  
**Dependencies**:4.1.

### Task 4.3 — Platform rate limiter

**Files**:`services/monitor_service.py`, Redis token bucket helper.  
**Acceptance Criteria**: Over-quota jobs are delayed; accounts are not rotated to evade limits.  
**Tests**:rate limit tests.  
**Dependencies**:4.1.

### Task 4.4 — Monitor actor

**Files**:`workers/monitor_actors.py`.  
**Acceptance Criteria**: Invoke the Adapter, insert a new Post, and write the Outbox.  
**Tests**:Mock integration test.  
**Dependencies**:2.7, 3.3, 4.2.

### Task 4.5 — Post dedup and lock

**Files**:Monitor Service.  
**Acceptance Criteria**: Repeated Polls / Webhooks do not create duplicate Posts.  
**Tests**:concurrency test.  
**Dependencies**:4.4.

### Task 4.6 — Creator CRUD and monitor APIs

**Files**:`api/v1/creators.py`, Service, Schemas.  
**Acceptance Criteria**: Create, pause, and poll-now are complete.  
**Tests**:API integration.  
**Dependencies**:4.4.

## Phase 5

### Task 5.1 — Content normalization

**Files**:`services/content_service.py`.  
**Acceptance Criteria**: Mock Posts convert to canonical PostContent.  
**Tests**:normalization fixtures.  
**Dependencies**:4.4.

### Task 5.2 — Prompt loader and manifest

**Files**:`prompts/manifest.yaml`, Prompt Loader.  
**Acceptance Criteria**: Load by name and version; persist the Hash.  
**Tests**:missing prompt and version tests.  
**Dependencies**:0.3.

### Task 5.3 — LLM provider interface and Mock provider

**Files**:`agents/provider.py`, `structured_output.py`.  
**Acceptance Criteria**: The Mock Provider can return fixed Structured Output.  
**Tests**:contract tests.  
**Dependencies**:5.2.

### Task 5.4 — Concrete Anchor Extractor

**Files**:`agents/anchor_extractor.py`, Prompt.  
**Acceptance Criteria**: Each candidate Post produces 1–5 Anchors or explicitly reports low confidence.  
**Tests**:caption fixtures.  
**Dependencies**:5.1, 5.3.

### Task 5.5 — Opportunity scoring rules

**Files**:`domain/scoring.py`, `services/opportunity_service.py`.  
**Acceptance Criteria**: The formula and relationship multiplier are correct.  
**Tests**:exact numeric unit tests.  
**Dependencies**:5.4.

### Task 5.6 — Opportunity Agent

**Files**:`agents/opportunity_agent.py`, Prompt.  
**Acceptance Criteria**: Structured Output; Hard Rules can override the model.  
**Tests**:model output validation.  
**Dependencies**:5.3, 5.5.

### Task 5.7 — Pipeline actor through opportunity decision

**Files**:`workers/pipeline_actors.py`.  
**Acceptance Criteria**: A Post can enter SKIPPED or GENERATING.  
**Tests**:integration state transition tests.  
**Dependencies**:5.6, 3.5.

## Phase 6

### Task 6.1 — Brand, Product, Campaign CRUD

**Files**:API routers/services/repositories.  
**Acceptance Criteria**: Approved/Forbidden Claims are configurable.  
**Tests**:API tests.  
**Dependencies**:1.4.

### Task 6.2 — Identity Profile APIs

**Files**:Account API and Service.  
**Acceptance Criteria**: Brand-official accounts cannot enable a consumer identity.  
**Tests**:validation tests.  
**Dependencies**:1.5.

### Task 6.3 — Voice Profile APIs

**Files**:Voice Service, Schemas.  
**Acceptance Criteria**: Versioning, enable/disable state, and approved examples can be stored.  
**Tests**:version tests.  
**Dependencies**:1.5.

### Task 6.4 — Comment prompts

**Files**:`comment_fast_v1.md`, `comment_normal_v1.md`, `comment_partner_v1.md`.  
**Acceptance Criteria**: The Prompt explicitly prohibits fabricated experiences, fictional identities, typo-based disguise, and Detector optimization.  
**Tests**:prompt policy snapshot test.  
**Dependencies**:5.2, 6.2, 6.3.

### Task 6.5 — Comment Agent

**Files**:`agents/comment_agent.py`, Schemas.  
**Acceptance Criteria**: One call returns two valid candidates and records anchors/claims/version.  
**Tests**:structured output tests.  
**Dependencies**:6.4, 5.3.

### Task 6.6 — Comment normalization and recent-history query

**Files**:`services/comment_service.py`, Repository.  
**Acceptance Criteria**: Retrieve history across account/campaign/creator dimensions.  
**Tests**:query tests.  
**Dependencies**:1.7.

### Task 6.7 — Similarity engine

**Files**:`agents/quality_evaluator.py`.  
**Acceptance Criteria**: exact, 3-gram, 2-gram, and prefix signature are computable.  
**Tests**:known similarity fixtures.  
**Dependencies**:6.6.

### Task 6.8 — Authenticity and quality rules

**Files**:`quality_evaluator.py`, `quality_service.py`.  
**Acceptance Criteria**: generic content, fake experience, fake identity, and unsupported claims are detectable.  
**Tests**: Corresponding Unit/Integration tests for E2E-004/005/006/007.  
**Dependencies**:6.5, 6.7.

### Task 6.9 — Comment generation pipeline

**Files**:Pipeline Actor.  
**Acceptance Criteria**:GENERATING → QUALITY_CHECKING → RISK_CHECKING/REVIEW/BLOCK.  
**Tests**:state integration.  
**Dependencies**:6.8, 1.8.

## Phase 7

### Task 7.1 — RuleRiskEngine

**Files**:`services/risk_service.py`.  
**Acceptance Criteria**: Hard Rules take precedence and are explainable.  
**Tests**:table-driven rules.  
**Dependencies**:6.8.

### Task 7.2 — LLMRiskAgent

**Files**:`agents/risk_agent.py`, Prompt.  
**Acceptance Criteria**: Invoke only when Rules are inconclusive; output ALLOW/REVIEW/BLOCK.  
**Tests**:provider fixtures.  
**Dependencies**:5.3, 7.1.

### Task 7.3 — Risk orchestration

**Files**:Risk Service.  
**Acceptance Criteria**: Persist the Final Decision; Fail Closed.  
**Tests**:Risk Agent outage test.  
**Dependencies**:7.2.

### Task 7.4 — Review Job model/service

**Files**:Review Service/API.  
**Acceptance Criteria**:claim, approve, edit-and-approve, reject.  
**Tests**:concurrent claim test.  
**Dependencies**:7.3.

### Task 7.5 — Provenance and disclosure workflow

**Files**:Comment/Review Service.  
**Acceptance Criteria**: Human edits update provenance; required-pending blocks automatic publishing.  
**Tests**:E2E-010.  
**Dependencies**:7.4.

## Phase 8

### Task 8.1 — Publish idempotency

**Files**:`services/publish_service.py`, Repository.  
**Acceptance Criteria**: Create only one Job for the same key.  
**Tests**:concurrent create test.  
**Dependencies**:1.7.

### Task 8.2 — Publish Router

**Files**:Publish Service.  
**Acceptance Criteria**: Return Official/Manual/Unsupported based on Capability.  
**Tests**:all capability states.  
**Dependencies**:2.2, 8.1.

### Task 8.3 — Mock Publish Actor

**Files**:`workers/publish_actors.py`.  
**Acceptance Criteria**: Publish Mock comments and store receipt/rank.  
**Tests**:E2E-001/002/003.  
**Dependencies**:2.7, 8.2.

### Task 8.4 — Publish uncertain and reconciliation

**Files**:Publish Actor/Service.  
**Acceptance Criteria**: success-but-timeout does not produce duplicates.  
**Tests**:E2E-009.  
**Dependencies**:8.3, 2.6.

### Task 8.5 — Manual Publish API

**Files**:Comments/Review API.  
**Acceptance Criteria**: Create a Manual Job; Operators can confirm published/skipped.  
**Tests**:API tests.  
**Dependencies**:8.2.

### Task 8.6 — Kill switches and limits

**Files**:System/Account/Campaign Service.  
**Acceptance Criteria**: Platform-, account-, and Campaign-level switches all take effect before external calls.  
**Tests**:E2E-011.  
**Dependencies**:8.2.

## Phase 9

### Task 9.1 — RunMode routing

**Files**:Pipeline Service.  
**Acceptance Criteria**: NORMAL/FAST/FIRST_COMMENT/TOP5 configuration takes effect.  
**Tests**:mode matrix.  
**Dependencies**:5.7, 6.9.

### Task 9.2 — Fast path timeout budget

**Files**:Agent Provider and Pipeline.  
**Acceptance Criteria**: Each Stage has an independent timeout; no generic fallback.  
**Tests**:timeout injection.  
**Dependencies**:9.1.

### Task 9.3 — Latency instrumentation

**Files**:`observability/timeline.py`, Metrics.  
**Acceptance Criteria**: All required timestamps and latency values are queryable.  
**Tests**:timeline metric test.  
**Dependencies**:3.5, 9.2.

### Task 9.4 — Rank analytics

**Files**:Metrics Service.  
**Acceptance Criteria**: First/Top5 and Coverage are calculated separately.  
**Tests**:unknown samples not counted as failures.  
**Dependencies**:8.3, 9.3.

### Task 9.5 — Performance benchmark

**Files**:`scripts/run_e2e_demo.py`, benchmark test.  
**Acceptance Criteria**: Mock FAST Path P95 meets this specification's target or produces a clear report.  
**Tests**:100 Post load test.  
**Dependencies**:9.4.

## Phase 10

### Task 10.1 — Frontend API client and auth

**Files**:`frontend/lib/api.ts`, Auth UI.  
**Acceptance Criteria**: Login and token refresh work.  
**Tests**:Playwright login.  
**Dependencies**:0.4, Auth API.

### Task 10.2 — SSE endpoint

**Files**:`api/v1/events.py`.  
**Acceptance Criteria**: Supports heartbeat, filter, and reconnect.  
**Tests**:SSE integration.  
**Dependencies**:3.5.

### Task 10.3 — Live page

**Files**:`frontend/app/live/page.tsx`.  
**Acceptance Criteria**: Displays the complete Timeline in real time.  
**Tests**:Playwright live flow.  
**Dependencies**:10.2.

### Task 10.4 — Review page

**Files**:Review UI.  
**Acceptance Criteria**: Fully displays candidates, anchors, quality, risk, identity, and disclosure.  
**Tests**:approve/edit/reject E2E.  
**Dependencies**:7.4, 10.1.

### Task 10.5 — Creator and Campaign pages

**Files**: Corresponding pages.  
**Acceptance Criteria**: CRUD and monitor controls work.  
**Tests**:Playwright CRUD.  
**Dependencies**:4.6, 6.1.

### Task 10.6 — Capabilities and Accounts pages

**Files**:Accounts/Settings UI.  
**Acceptance Criteria**: Capability, Identity, Auth, and Kill Switch are visible.  
**Tests**:Playwright.  
**Dependencies**:6.2, 8.6.

### Task 10.7 — Analytics page

**Files**:Analytics UI.  
**Acceptance Criteria**:Latency, Quality, Risk, First/Top5 Coverage.  
**Tests**:fixture visual test.  
**Dependencies**:9.4.

## Phase 11

### Task 11.1 — Encryption and secret handling

**Files**:`core/encryption.py`, Account Service.  
**Acceptance Criteria**: Token round-trip succeeds; logs contain no plaintext.  
**Tests**:encryption and log-redaction tests.  
**Dependencies**:1.5.

### Task 11.2 — RBAC

**Files**:Auth dependencies.  
**Acceptance Criteria**: Role permissions match Section 30.  
**Tests**:role matrix API tests.  
**Dependencies**:10.1.

### Task 11.3 — Audit logs

**Files**:`models/audit.py`, Audit Service.  
**Acceptance Criteria**: All critical actions write audit records.  
**Tests**:review/publish/kill-switch audit tests.  
**Dependencies**:11.2.

### Task 11.4 — Circuit breaker and DLQ

**Files**:Worker Middleware, Health Service.  
**Acceptance Criteria**: Repeated failures open the Circuit; jobs enter the DLQ.  
**Tests**:failure injection.  
**Dependencies**:2.6, 8.4.

### Task 11.5 — Observability dashboard APIs

**Files**:System/Metrics API.  
**Acceptance Criteria**: Queue, Worker, Polling, LLM, and Publish metrics are available.  
**Tests**:metrics endpoint tests.  
**Dependencies**:9.3, 11.4.

### Task 11.6 — Full DoD E2E

**Files**:`tests/e2e/test_full_demo.py`, `scripts/run_e2e_demo.py`.  
**Acceptance Criteria**: The fully automated path from Brand creation to rank display passes.  
**Tests**:`make test-e2e`.  
**Dependencies**: Other tasks in Phases 0–11.

## Phase 12

### Task 12.1 — Real Adapter capability template

**Files**: Each platform's `CAPABILITIES.md`.  
**Acceptance Criteria**: Every capability has a status, source, date, Scope, and limitations.  
**Tests**:documentation schema check.  
**Dependencies**:0.2, 2.1.

### Task 12.2 — Douyin client skeleton

**Files**:`platforms/douyin/client.py`, `adapter.py`.  
**Implementation**: Implement only authorized read/reply endpoints confirmed by official documentation; third-party top-level comments remain UNKNOWN.  
**Acceptance Criteria**: Unauthorized access returns an explicit error; no browser fallback.  
**Tests**:mocked official API contract tests.  
**Dependencies**:12.1, 2.1.

### Task 12.3 — Xiaohongshu adapter skeleton

**Files**: Corresponding Adapter and Capability documentation.  
**Acceptance Criteria**: Unknown social capabilities raise Unknown/Unsupported; do not fabricate endpoints.  
**Tests**:contract tests.  
**Dependencies**:12.1.

### Task 12.4 — WeChat Channels adapter skeleton

**Files**: Corresponding Adapter and Capability documentation.  
**Acceptance Criteria**: Same as above.  
**Tests**:contract tests.  
**Dependencies**:12.1.

### Task 12.5 — Capability verification script

**Files**:`scripts/verify_capabilities.py`.  
**Acceptance Criteria**: Output the Matrix and expired capabilities; never automatically upgrade UNKNOWN to SUPPORTED.  
**Tests**:fixture test.  
**Dependencies**:12.2–12.4.

---

# 35. Acceptance Tests

## 35.1 Repository Acceptance

```bash
make lint
make typecheck
make test
npm --prefix frontend run build
```

All exit codes are 0.

## 35.2 Local Runtime Acceptance

```bash
docker compose up --build
```

The following must hold:

1. API health 200.
2. Frontend is accessible.
3. Worker heartbeat is healthy.
4. Scheduler is healthy.
5. PostgreSQL and Redis readiness are healthy.

## 35.3 Product Acceptance

1. Create Brand A.
2. Create a Brand Official Account and an authentic Identity Profile.
3. Create a Voice Profile.
4. Create a Campaign.
5. Create a target Creator.
6. Start monitoring.
7. The Mock Creator publishes a cashmere-outfit Post.
8. The Monitor detects the Post.
9. The system extracts at least one concrete Anchor.
10. The Opportunity Score reaches the threshold.
11. The Comment Agent generates two non-templated candidates.
12. The Quality Evaluator validates context, authenticity, and deduplication.
13. The Risk Engine allows or routes to Review.
14. The Publish Router publishes to the Mock Platform.
15. The UI displays the complete Timeline.
16. The system calculates Rank.
17. Analytics displays First/Top5 and Coverage.
18. Audit logs record generation provenance and approval information.

## 35.4 Safety Acceptance

The following tests must pass:

- Any automated candidate containing a fake purchase experience must not be published.
- A brand account must not speak as an ordinary consumer.
- Capability UNKNOWN must not invoke an external publishing API.
- AI disclosure pending must block automatic publishing.
- The project contains no detector-evasion scores, Prompts, or endpoints.
- The project contains no CAPTCHA, device-fingerprint, or browser-simulated publishing module.

---

# 36. Definition of Done

MVP completion requires all of the following:

```text
[ ] One-command startup with docker compose
[ ] Mock Platform runs completely
[ ] Creator Monitor discovers new Posts
[ ] Dynamic Polling is testable
[ ] Fast/Slow Path is switchable
[ ] Concrete Anchors are generated
[ ] Opportunity Score is explainable
[ ] Comment Agent Structured Output
[ ] Account Identity constraints take effect
[ ] Brand Voice takes effect
[ ] Quality Evaluator takes effect
[ ] Fake Experience / Fake Identity is blocked
[ ] Duplicate Detection takes effect
[ ] Risk Engine takes effect
[ ] Review UI is usable
[ ] Publish Router does not invoke unsupported capabilities
[ ] Mock Publish is idempotent
[ ] Publish Uncertain can be Reconciled
[ ] SSE Live Timeline is usable
[ ] First / Top5 + Coverage is available
[ ] Token encryption and RBAC are available
[ ] Audit Log is available
[ ] Complete automated E2E tests PASS
[ ] NON_GOALS and Capability documentation are complete
```

---

# 37. Implementation Order

For the exact execution order, see:

```text
IMPLEMENTATION_ORDER.md
```

Codex / Claude Code must execute each item in order, must not skip prerequisites, and must not implement unverified automatic publishing paths before real-platform Adapters.

---

# 38. Policy and Research Notes

The engineering design must continuously observe these baseline rules:

1. Platforms generally impose explicit restrictions on spam, excessive marketing, irrelevant comments, and evasion of technical review.
2. Unauthorized automation, fraudulent registration, bulk registration, and improper data acquisition must not be product paths.
3. Current Chinese rules for labeling AI-generated synthetic content cover text and other content, require disclosure and use of platform labeling features where applicable, and prohibit malicious removal, alteration, falsification, or concealment of those labels.
4. Because applicability may vary for short comments, human edits, platform capabilities, and specific business scenarios, the final disclosure policy must be confirmed against platform rules and by Legal; the system must retain support and must not conceal by default.
5. Every real-platform capability must record its evidence source, verification date, Scope, and expiration time.

---

# Part II — Implementation Order

# FirstComment Agent — Implementation Order

Execute strictly in dependency order. After completing each item, run its corresponding tests before checking it off.

## Bootstrap

- [ ] 001 create repository skeleton
- [ ] 002 add README, ENGINEERING_SPEC, NON_GOALS and PLATFORM_CAPABILITIES
- [ ] 003 configure backend pyproject dependencies
- [ ] 004 configure Ruff, mypy and pytest
- [ ] 005 initialize Next.js TypeScript strict frontend
- [ ] 006 add root Makefile
- [ ] 007 add `.env.example`
- [ ] 008 add Dockerfiles
- [ ] 009 add docker-compose PostgreSQL and Redis
- [ ] 010 add API health endpoint
- [ ] 011 verify `docker compose up` and health 200

## Core Infrastructure

- [ ] 012 implement Pydantic Settings
- [ ] 013 implement JSON structured logging
- [ ] 014 implement trace-id middleware
- [ ] 015 implement async SQLAlchemy session
- [ ] 016 configure Alembic
- [ ] 017 verify empty database migration
- [ ] 018 implement domain enums
- [ ] 019 implement capability models
- [ ] 020 implement common timestamps and UUID mixins

## Domain Models

- [ ] 021 implement User and RBAC enums
- [ ] 022 implement Brand model and schemas
- [ ] 023 implement Product model and schemas
- [ ] 024 implement Campaign model and schemas
- [ ] 025 implement AccountIdentityProfile model
- [ ] 026 add identity database constraints
- [ ] 027 implement VoiceProfile model
- [ ] 028 implement BrandAccount model and encrypted credential fields
- [ ] 029 implement Creator model
- [ ] 030 implement CreatorPlatformAccount model
- [ ] 031 implement Post model with unique external key
- [ ] 032 implement PostContent model
- [ ] 033 implement PostAnchor model
- [ ] 034 implement OpportunityEvaluation model
- [ ] 035 implement CommentCandidate model
- [ ] 036 implement CommentQualityEvaluation model
- [ ] 037 assert no detector-evasion fields in schema
- [ ] 038 implement RiskEvent model
- [ ] 039 implement ReviewJob model
- [ ] 040 implement PublishJob model with idempotency key
- [ ] 041 implement PublishedComment model
- [ ] 042 implement MetricEvent and AuditLog models
- [ ] 043 generate and apply initial migration

## State and Repository Layer

- [ ] 044 implement allowed state transition map
- [ ] 045 implement transition guard
- [ ] 046 add exhaustive state-machine unit tests
- [ ] 047 implement base repository
- [ ] 048 implement Brand/Product/Campaign repositories
- [ ] 049 implement Creator/Post repositories
- [ ] 050 implement Comment/Publish repositories
- [ ] 051 implement transaction helpers

## Platform Abstraction

- [ ] 052 implement PlatformAdapter abstract contract
- [ ] 053 implement platform exception mapping
- [ ] 054 implement PlatformRegistry
- [ ] 055 add adapter contract test suite

## Mock Platform

- [ ] 056 implement Mock Creator storage and API
- [ ] 057 implement Mock Post storage and API
- [ ] 058 implement Mock Comment storage and API
- [ ] 059 implement chronological rank
- [ ] 060 test rank 1, rank 4 and rank 6
- [ ] 061 implement visible ranking strategies
- [ ] 062 make personalized ranking seed deterministic
- [ ] 063 implement latency injection
- [ ] 064 implement 429 and 500 injection
- [ ] 065 implement timeout injection
- [ ] 066 implement success-but-timeout publish injection
- [ ] 067 implement MockPlatformAdapter
- [ ] 068 run full adapter contract suite for Mock

## Queue and Events

- [ ] 069 configure Dramatiq Redis broker
- [ ] 070 enable AsyncIO middleware
- [ ] 071 add critical/high/normal/low queues
- [ ] 072 implement event envelope
- [ ] 073 implement OutboxEvent model
- [ ] 074 implement transactional outbox writer
- [ ] 075 implement outbox relay with `SKIP LOCKED`
- [ ] 076 test concurrent outbox relays
- [ ] 077 implement Timeline event writer
- [ ] 078 persist state changes to timeline

## Scheduler and Monitor

- [ ] 079 implement Redis ZSET polling schedule
- [ ] 080 implement atomic due-job pop
- [ ] 081 implement deterministic jitter
- [ ] 082 implement AdaptivePollingPolicy
- [ ] 083 test normal/warm/hot intervals
- [ ] 084 test failure backoff and rate-pressure slowdown
- [ ] 085 implement creator polling lock
- [ ] 086 implement platform token-bucket limiter
- [ ] 087 implement monitor actor
- [ ] 088 insert unseen posts and outbox in one transaction
- [ ] 089 test duplicate poll does not duplicate Post
- [ ] 090 implement Creator CRUD API
- [ ] 091 implement monitor/pause/poll-now API

## Content and Opportunity

- [ ] 092 implement content normalization
- [ ] 093 implement Prompt manifest and loader
- [ ] 094 persist prompt version and hash
- [ ] 095 implement LLM Provider interface
- [ ] 096 implement deterministic Mock LLM Provider
- [ ] 097 implement Structured Output validation
- [ ] 098 implement one-time structured-output repair
- [ ] 099 create anchor extraction prompt
- [ ] 100 implement Concrete Anchor Extractor
- [ ] 101 test 1–5 anchors and low-confidence path
- [ ] 102 implement Opportunity formula
- [ ] 103 implement relationship multiplier
- [ ] 104 implement Opportunity Agent
- [ ] 105 implement hard-rule override
- [ ] 106 wire Post to SKIPPED or GENERATING state

## Brand, Identity and Voice

- [ ] 107 implement Brand CRUD API
- [ ] 108 implement Product and approved-claim API
- [ ] 109 implement Campaign CRUD and activation
- [ ] 110 implement Identity Profile API
- [ ] 111 prevent brand account consumer impersonation
- [ ] 112 implement Voice Profile API and versions
- [ ] 113 add approved examples and forbidden phrases

## Comment Generation

- [ ] 114 create fast comment prompt
- [ ] 115 create normal comment prompt
- [ ] 116 create partner comment prompt
- [ ] 117 add explicit no-fake-experience rules
- [ ] 118 add explicit no-fake-persona rules
- [ ] 119 add explicit no-detector-evasion rules
- [ ] 120 implement Comment Agent structured output
- [ ] 121 generate two candidates in one call
- [ ] 122 persist referenced anchors and claims
- [ ] 123 query recent comments by account/campaign/creator
- [ ] 124 implement comment normalization

## Authenticity and Quality

- [ ] 125 implement exact normalized duplicate check
- [ ] 126 implement character 3-gram Jaccard
- [ ] 127 implement word 2-gram Jaccard
- [ ] 128 implement prefix and CTA signatures
- [ ] 129 implement generic-praise detection
- [ ] 130 implement anchor-coverage check
- [ ] 131 implement unsupported-claim check
- [ ] 132 implement fake-experience detection
- [ ] 133 implement fake-identity detection
- [ ] 134 implement voice-profile compliance
- [ ] 135 implement intentional-typo-pattern block
- [ ] 136 implement quality score
- [ ] 137 implement allow/review/block thresholds
- [ ] 138 test duplicate, generic, fake-experience and identity cases
- [ ] 139 verify schema and metrics contain no detector score

## Risk and Review

- [ ] 140 implement RuleRiskEngine
- [ ] 141 block competitor and blocked creators
- [ ] 142 block unsupported capability auto-publish
- [ ] 143 enforce daily account and creator limits
- [ ] 144 enforce disclosure-pending gate
- [ ] 145 create LLM risk prompt
- [ ] 146 implement LLMRiskAgent
- [ ] 147 call LLM risk only for uncertain cases
- [ ] 148 implement Fail Closed behavior
- [ ] 149 implement Review Job service
- [ ] 150 implement review list/detail APIs
- [ ] 151 implement claim/approve/edit/reject APIs
- [ ] 152 update content provenance after human edit
- [ ] 153 audit all review decisions

## Publishing

- [ ] 154 implement publish idempotency-key builder
- [ ] 155 implement atomic PublishJob creation
- [ ] 156 implement Publish Router
- [ ] 157 route UNKNOWN top-level capability to manual
- [ ] 158 implement Mock Publish Actor
- [ ] 159 persist external receipt and rank
- [ ] 160 implement PUBLISH_UNCERTAIN state
- [ ] 161 implement reconcile-before-retry
- [ ] 162 test success-but-timeout produces one comment
- [ ] 163 implement Manual Publish Workflow API
- [ ] 164 implement manual published/skipped confirmation
- [ ] 165 implement platform kill switch
- [ ] 166 implement account kill switch
- [ ] 167 implement campaign kill switch
- [ ] 168 verify kill switches run before external calls

## Fast Path and Metrics

- [ ] 169 implement RunMode routing
- [ ] 170 implement stage-specific timeouts
- [ ] 171 prohibit generic fallback on timeout
- [ ] 172 implement all timeline timestamps
- [ ] 173 compute all latency metrics
- [ ] 174 implement First Comment metric
- [ ] 175 implement Top5 metric
- [ ] 176 implement measurement coverage
- [ ] 177 verify UNKNOWN samples are excluded from denominator
- [ ] 178 implement quality metrics
- [ ] 179 implement risk and publish metrics
- [ ] 180 add 100-post Mock performance benchmark

## Backend APIs and Auth

- [ ] 181 implement User model and password hashing
- [ ] 182 implement login and `/auth/me`
- [ ] 183 implement RBAC dependencies
- [ ] 184 implement Posts list/detail/timeline API
- [ ] 185 implement Comments candidate/published API
- [ ] 186 implement Metrics overview/latency/quality/ranking APIs
- [ ] 187 implement System health/readiness/queues APIs
- [ ] 188 implement Capability Matrix API
- [ ] 189 implement consistent error envelope

## SSE and Frontend

- [ ] 190 implement SSE stream endpoint
- [ ] 191 add heartbeat and reconnect support
- [ ] 192 implement frontend API client
- [ ] 193 implement login page
- [ ] 194 implement Dashboard page
- [ ] 195 implement Creator page
- [ ] 196 implement Live Timeline page
- [ ] 197 implement Posts page
- [ ] 198 implement Review page
- [ ] 199 display anchors, identity, quality and risk
- [ ] 200 implement edit-and-approve flow
- [ ] 201 implement Comments page
- [ ] 202 implement Campaign and Brand pages
- [ ] 203 implement Accounts and Identity page
- [ ] 204 implement Capability and Kill Switch page
- [ ] 205 implement Analytics page
- [ ] 206 add Playwright CRUD tests
- [ ] 207 add Playwright full review flow

## Security and Reliability

- [ ] 208 implement AES-GCM credential encryption
- [ ] 209 implement token log redaction
- [ ] 210 implement AuditLog service
- [ ] 211 audit identity, voice, review, publish and kill-switch changes
- [ ] 212 implement circuit breaker
- [ ] 213 implement dead-letter persistence
- [ ] 214 implement worker heartbeats
- [ ] 215 implement stuck-job reconciliation
- [ ] 216 implement expired-review cleanup
- [ ] 217 implement retention jobs
- [ ] 218 run failure-injection integration suite

## Real Platform Skeletons

- [ ] 219 create per-platform CAPABILITIES template
- [ ] 220 create Douyin client skeleton
- [ ] 221 implement only verified authorized read/reply methods
- [ ] 222 keep arbitrary third-party top-level comment UNKNOWN
- [ ] 223 create Xiaohongshu adapter skeleton
- [ ] 224 keep unverified social operations UNKNOWN
- [ ] 225 create WeChat Channels adapter skeleton
- [ ] 226 keep unverified social operations UNKNOWN
- [ ] 227 implement capability verification script
- [ ] 228 add adapter contract tests for unsupported methods
- [ ] 229 verify no browser/emulator/private-API fallback exists

## Final Acceptance

- [ ] 230 run backend lint and typecheck
- [ ] 231 run backend unit tests
- [ ] 232 run integration tests with PostgreSQL and Redis
- [ ] 233 run adapter contract tests
- [ ] 234 run all required E2E cases
- [ ] 235 run frontend lint and build
- [ ] 236 run Playwright tests
- [ ] 237 run full Docker Compose demo
- [ ] 238 verify First/Top5 and Coverage on Dashboard
- [ ] 239 verify fake consumer comment is blocked
- [ ] 240 verify capability UNKNOWN routes to manual
- [ ] 241 verify no detector-evasion metric, prompt or module exists
- [ ] 242 verify audit and provenance records
- [ ] 243 update README and all docs
- [ ] 244 tag MVP v0.1.0

---

# Part III — Non-Goals and Production Safety Boundaries

# FirstComment Agent — Non-Goals

This document defines the production safety boundary. No development Agent, engineer, or contractor may bypass it.

## 1. Do Not Implement Detection Evasion

- Do not optimize AI Detector pass rates.
- Do not build a “human probability” or “stealth score.”
- Do not reverse-engineer evasive writing styles from platform moderation outcomes.
- Do not evade moderation through character substitution, homophones, typos, or random grammatical errors.
- Do not remove, alter, hide, or falsify AI labels, provenance labels, or audit information.

## 2. Do Not Impersonate Human Consumers

- Brand accounts must not impersonate ordinary consumers.
- Do not generate fabricated purchases, usage, occupations, ages, genders, locations, family histories, or social experiences.
- Do not create fabricated life histories or Personas.
- Do not make bot accounts simulate the long-term behavioral history of a “real personal account.”

## 3. Do Not Bypass Platform Risk Controls

- Do not bypass CAPTCHAs.
- Do not spoof device fingerprints.
- Do not use emulators, hooks, reverse engineering, private APIs, or concealed browser automation for publishing.
- Do not evade bans, automatically rotate accounts, farm accounts, or perform bulk registration.
- Do not defeat anti-scraping, anti-bot, or Rate Limit controls.

## 4. Do Not Manufacture Fake Engagement

- Do not fabricate likes, follows, replies, saves, or views.
- Do not post irrelevant comments in bulk.
- Do not impersonate users in competitors' comment sections to divert traffic.
- Do not publish repetitive, low-quality, context-free advertising templates.

## 5. Permitted and Required Alternatives

- Authentic Brand Voice.
- Context-anchored comments.
- Non-templated quality controls.
- Authentic account identity and disclosure policies.
- Human-in-the-loop.
- Official API / Official Partner Capability.
- Manual Publish Workflow.
- Anti-spam, deduplication, frequency controls, auditing, and Kill Switches.

If any new requirement conflicts with this document, development stops by default and requires joint review by Product, Security, and Compliance.

---

# Part IV — Platform Capability Matrix

# Platform Capabilities Registry

**Baseline date**: 2026-09-02

Status definitions:

```text
SUPPORTED
CONDITIONAL
AUTH_REQUIRED
MANUAL
UNSUPPORTED
UNKNOWN
RATE_LIMITED
DISABLED
```

## Global Rules

1. `UNKNOWN` must not be treated as `SUPPORTED` in code.
2. Reply Comment must not be treated as Top-level Comment.
3. Without an official or formal Partner Capability, the system may only enter a Manual Workflow.
4. An Adapter must not fall back to browser, emulator, private-API, or device automation.
5. Every capability verification must record its source, date, Scope, account type, and expiration.

## Mock Platform

| Capability | Status | Notes |
| ---|---|---|
| Creator Monitoring | SUPPORTED | Fully simulated |
| New Post Event | SUPPORTED | API/Event |
| Post Fetch | SUPPORTED | Fully simulated |
| Comment Read | SUPPORTED | Fully simulated |
| Top-level Comment | SUPPORTED | Fully simulated |
| Comment Reply | SUPPORTED | Fully simulated |
| Chronological Rank | SUPPORTED | Exact |
| Visible Rank | SUPPORTED | Configurable simulation |

## Douyin

| Capability | Initial Status | Notes |
| ---|---|---|
| Authorized Account Video Read | CONDITIONAL | Requires official application permissions and user authorization |
| Keyword Video Search | CONDITIONAL | Limited by keywords, time range, and Scope |
| Comment List | CONDITIONAL | Depends on the endpoint and authorization scope |
| Comment Reply | CONDITIONAL | Official documentation provides reply capability; permissions/authorization required |
| Arbitrary Third-party Top-level Comment | UNKNOWN | Must not be inferred from Reply capability |
| New Post Webhook for Arbitrary Creator | UNKNOWN | Unverified |
| Visible Comment Rank | UNKNOWN | Must not be estimated as exact |

## Xiaohongshu

| Capability | Initial Status | Notes |
| ---|---|---|
| Arbitrary Creator Monitoring | UNKNOWN | Awaiting written confirmation from the platform or Partner |
| New Post Webhook | UNKNOWN | Awaiting confirmation |
| Third-party Comment Read | UNKNOWN | Awaiting confirmation |
| Third-party Top-level Comment | UNKNOWN | Awaiting confirmation |
| Visible Comment Rank | UNKNOWN | Awaiting confirmation |

## WeChat Channels

| Capability | Initial Status | Notes |
| ---|---|---|
| Arbitrary Creator Monitoring | UNKNOWN | Awaiting written confirmation from the platform or Partner |
| New Post Webhook | UNKNOWN | Awaiting confirmation |
| Third-party Comment Read | UNKNOWN | Awaiting confirmation |
| Third-party Top-level Comment | UNKNOWN | Awaiting confirmation |
| Visible Comment Rank | UNKNOWN | Awaiting confirmation |

## Capability Record Template

```yaml
platform: DOUYIN
capability: COMMENT_REPLY
status: CONDITIONAL
verified_at: 2026-09-02
expires_at: null
source_title: "Official documentation title"
source_owner: "Platform operator"
scope:
  account_types: []
  target_content_types: []
  authorization_required: true
limitations: []
verified_by: "name"
```
