# Deployment

Docker Compose is the supported MVP deployment target. It starts:

```text
postgres · redis · minio · backend-api
worker-critical · worker-default · worker-low
scheduler · outbox-relay · frontend · prometheus
```

## Local deployment

```bash
cp .env.example .env
# Generate APP_SECRET_KEY, TOKEN_ENCRYPTION_KEY, MinIO credentials, and any provider keys.
docker compose up --build -d
make migrate
```

Inspect `docker compose ps` and `/api/v1/system/readiness` before seeding or processing posts. Readiness covers PostgreSQL, Redis, the outbox relay heartbeat, and the critical worker heartbeat.

## Queue ownership

- `worker-critical`: new post and publish requests.
- `worker-default`: high and normal monitoring/pipeline tasks.
- `worker-low`: analytics and historical reconciliation.

Workers may be scaled independently, but only one logical scheduler claim may own a due polling item. Locks and schedules require expiry/recovery paths.

## Production requirements

- Pin container images by version or digest.
- Terminate TLS at a trusted ingress and restrict CORS.
- Store secrets outside Compose files and rotate encryption keys deliberately.
- Use managed backups and test PostgreSQL restore procedures.
- Restrict MinIO buckets and apply the approved media retention policy.
- Persist Prometheus data or forward metrics to the organization’s monitoring system.
- Alert on queue age, unpublished outbox age, circuit breaker state, auth expiry, stale capability evidence, and `PUBLISH_UNCERTAIN` jobs.

The Compose fallback secrets exist only to make configuration rendering predictable. The application should reject unsafe defaults outside development.
