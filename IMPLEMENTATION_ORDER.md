# FirstComment Agent — Implementation Order

严格按依赖顺序执行。每完成一项，运行对应测试后再勾选。

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
