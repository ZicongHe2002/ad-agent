# FirstComment Agent

FirstComment Agent is a local-first, policy-aware workspace for detecting creator posts, generating context-grounded comment suggestions, reviewing identity and commercial risk, and publishing only through verified official capabilities or a human-assisted workflow.

The MVP is a modular monolith with a FastAPI backend, Dramatiq workers, PostgreSQL, Redis, a complete Mock Platform, and a Next.js operations console.

## Safety boundary

This project is designed around **Natural, Specific, Context-Grounded, Truthful and Account-Consistent** communication. It does not implement detector evasion, fake consumer identities or experiences, AI-label removal, CAPTCHA bypass, device fingerprint spoofing, account farming, or unverified private APIs. `UNKNOWN` capability never means `SUPPORTED`. Normal logged-in browser interaction is being evaluated as a separate sending channel; it is not implemented or verified for production.

See [NON_GOALS.md](NON_GOALS.md) and [PLATFORM_CAPABILITIES.md](PLATFORM_CAPABILITIES.md) before adding an integration.

## Quick start

Requirements:

- Docker with Docker Compose v2
- At least 6 GB of available memory for the complete local stack

Create local configuration and fill every blank secret with a unique value:

```bash
cp .env.example .env
```

Start infrastructure and application services:

```bash
docker compose up --build -d
make migrate
make seed-demo
```

Open:

- Operations console: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/api/v1/system/health>
- MinIO console: <http://localhost:9001>
- Prometheus: <http://localhost:9090>

Follow service logs with `make logs`; stop the stack with `make down`.

## Local development

Install backend and frontend dependencies:

```bash
make install
```

Run the frontend separately:

```bash
npm --prefix frontend run dev
```

The browser client reads `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000/api/v1`. Authentication uses a bearer access token; when the backend supplies a refresh token, the unified client performs one refresh attempt after a 401. The Live page consumes the authenticated SSE endpoint and reconnects with exponential backoff and `Last-Event-ID`.

## Frontend routes

The App Router console includes:

```text
/login        /dashboard     /creators      /live
/posts        /review        /comments      /campaigns
/brand        /accounts      /risk          /analytics
/settings
```

Review shortcuts select candidates or open a confirmation dialog. They never directly publish, approve, or skip content. Edited text must return through mandatory identity, claim, quality, duplicate, disclosure, and risk checks.

## Testing and automatic operation

Run `make migrate` after upgrading: migration `0004_publishing_settings` stores each workspace's publishing policy. In Settings, choose **REVIEW** while testing; every eligible candidate is reviewed before publishing. Choose **AUTO** for unattended operation after testing, enable automatic publishing on the intended account, and turn off that campaign's `human_review_required` override. Existing review jobs are never approved by switching modes.

AUTO publishes only candidates that pass quality, risk, account authorization, disclosure, current platform capability, quota, and kill-switch checks. Unresolved candidates are skipped with reasons in their timeline instead of creating a new review queue. Switching back to REVIEW also blocks queued automatic jobs before their next external call.

The optional automatic disclosure setting adds the declared public account identity and `AI辅助生成` visibly to the actual comment when the identity requires them. The complete outgoing text is checked again. This records a text disclosure; it does not claim a platform label was applied or replace a platform-specific disclosure requirement.

The Accounts and Settings pages distinguish a configured account from an available sending integration. Xiaohongshu and Douyin top-level comment publishing is not connected merely by adding an account or turning on AUTO. The current platform status includes the missing integration/capability reason. The browser-based alternative and its verification gaps are documented in [the browser publishing research](docs/browser-publishing-research-2026-09-19.md).

For a real model, set `LLM_PROVIDER=openai`, `LLM_API_KEY`, and real `LLM_MODEL_FAST` / `LLM_MODEL_NORMAL` IDs in server configuration. `LLM_API_BASE` defaults to `https://api.openai.com/v1`; `LLM_TIMEOUT_SECONDS` controls requests. The provider uses the Responses API with structured output and `store=false`. Missing credentials, unsupported providers, refusals, and incomplete responses never silently fall back to generated Mock comments. Keep `LLM_PROVIDER=mock` for network-free testing. See [OpenAI structured output documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Tests and quality checks

```bash
make lint
make typecheck
make test-unit
make test-integration
make test-contract
make test-e2e
make test
npm --prefix frontend run build
```

The required test scenarios and acceptance criteria are defined in [ENGINEERING_SPEC.md](ENGINEERING_SPEC.md). The exact dependency order is in [IMPLEMENTATION_ORDER.md](IMPLEMENTATION_ORDER.md).

## Service topology

Docker Compose starts PostgreSQL, Redis, MinIO, the API, critical/default/low workers, polling scheduler, outbox relay, frontend, and Prometheus. PostgreSQL is the source of truth; Redis provides queues, schedules, locks, and ephemeral coordination. External platforms are isolated behind explicit capability-aware adapters.

Operational and design notes live in [docs/](docs/):

- [Architecture](docs/architecture.md)
- [Database](docs/database.md)
- [Platform adapters](docs/platform-adapters.md)
- [Agents](docs/agents.md)
- [API](docs/api.md)
- [Development](docs/development.md)
- [Deployment](docs/deployment.md)
- [Security](docs/security.md)
- [Capability policy](docs/platform-capabilities.md)

## Secrets and production use

Never commit `.env`, platform credentials, LLM keys, access tokens, or encryption keys. Development defaults in Compose are not production credentials. Production deployments must use a secret manager, TLS, restricted CORS origins, encrypted database backups, tested key rotation, RBAC, audit retention, and current platform/legal review.

Real-platform auto-publishing stays disabled until the exact operation, account scope, authorization, evidence source, verification date, and expiry are all recorded and current. When capability or disclosure requirements are unresolved, the system fails closed or creates a manual workflow.
