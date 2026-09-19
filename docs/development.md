# Development

## Prerequisites

- Python 3.12+
- Node.js 22+
- Docker with Compose v2
- PostgreSQL 16 and Redis 7 when running without Compose

## Setup

```bash
cp .env.example .env
make install
docker compose up -d postgres redis minio
make migrate
```

Run the API and frontend using their package commands, or use `make up` for the complete stack. Do not reuse development secrets in a shared or production environment.

## Quality workflow

Before handing off a change:

```bash
make lint
make typecheck
make test-unit
make test-integration
make test-contract
npm --prefix frontend run build
```

Run `make test-e2e` with the complete stack. Contract tests cover every capability state and verify that no adapter invokes browser automation. Integration tests use real PostgreSQL and Redis rather than replacing transaction/locking behavior with mocks.

## Frontend conventions

- App Router pages live under `frontend/app/`.
- Shared visual primitives live in `frontend/components/`.
- All HTTP calls go through `frontend/lib/api.ts`.
- Authenticated streaming goes through `frontend/lib/sse.ts`.
- Interactive pages explicitly use `"use client"`; informational pages remain server components.
- TypeScript strict mode and `noUncheckedIndexedAccess` stay enabled.

Example rows make the initial console legible when no local data has been seeded. They are visibly marked on the Live page and must not be presented as real analytics.

## Change discipline

Schema changes require migrations. Prompt changes require a new version/hash and snapshot tests. Capability changes require evidence, owner, scope, verification date, expiry, and audit log. Safety gates cannot be weakened solely to meet latency or volume targets.
