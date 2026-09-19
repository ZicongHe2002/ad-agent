# Database

PostgreSQL is the source of truth for domain state, policy decisions, audit records, publish receipts, and event delivery state. Redis data is coordination state and must be reconstructible.

## Main data chain

```text
Brand ─┬─ Product
       ├─ Campaign
       └─ BrandAccount ─ IdentityProfile / VoiceProfile

Creator ─ CreatorPlatformAccount ─ Post ─ PostContent / PostAnchor
                                      └─ OpportunityEvaluation
                                         └─ CommentCandidate
                                            ├─ QualityEvaluation
                                            ├─ RiskEvent
                                            ├─ ReviewJob
                                            └─ PublishJob ─ PublishedComment
```

## Required uniqueness

- `(platform, external_post_id)`
- `(platform, external_creator_id)`
- `(platform, external_account_id)`
- `(post_id, campaign_id)` for the current opportunity evaluation
- `publish_jobs.idempotency_key`
- `published_comments.publish_job_id`

The publish key is derived from the tenant/workspace, platform, publishing account, external post, campaign, and intent. Creating the key and publish job must be concurrency-safe.

## Transaction and delivery rules

- Post insertion and its outbox event are committed together.
- Queue messages are at-least-once; consumers must be idempotent.
- A worker acknowledges only after required database writes commit.
- `PUBLISH_UNCERTAIN` is reconciled before retry.
- State changes go through the domain state machine and create timeline/audit records.

## Migrations

Every schema change uses Alembic. CI upgrades an empty database to `head`; rollback is tested in non-production environments. Destructive production changes require an expand/migrate/contract sequence, and enum changes remain isolated migrations.

Sensitive credential material is stored only as authenticated ciphertext with a nonce and key version. Audit before/after payloads must redact credential and token fields.
