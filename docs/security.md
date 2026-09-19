# Security

## Identity and access

Roles are ADMIN, BRAND_MANAGER, REVIEWER, and VIEWER. Only ADMIN may change capability records or kill switches. Reviewers can make review decisions but cannot read or update platform credentials. Every authorization check is enforced by the API; hiding a frontend control is not authorization.

Login, failed login, role change, credential update, identity/voice change, review decision, comment edit, publish action, capability change, and kill-switch change are audited.

## Secrets

- Platform credentials use AES-256-GCM authenticated encryption.
- Store ciphertext, nonce, and key version; the master key comes from a secret manager or protected environment injection.
- Redact tokens, passwords, authorization headers, cookies, and ciphertext metadata from logs and audit payloads.
- Never expose provider or platform credentials through `NEXT_PUBLIC_*` variables.
- Access and refresh tokens have bounded lifetimes and are cleared after refresh failure.

## Publishing safety

Before an external call, verify current capability evidence, account identity, active campaign, authorization scope, disclosure status, quality/risk decisions, idempotency lock, rate-limit token, and every applicable kill switch. Unavailable policy, identity, claim, capability, disclosure, or risk dependencies fail closed.

An ambiguous network result is not safe to retry. Move it to `PUBLISH_UNCERTAIN`, reconcile, and only retry after a definite not-published result.

## Privacy and content

Do not build sensitive profiles of ordinary users. Retain only data needed for context, traceability, and measurable product behavior. Do not retain full third-party media indefinitely; apply platform authorization and company retention rules.

AI provenance is always retained internally. Required platform or legal disclosures must be applied or confirmed before publishing. There is no code path for removing, hiding, falsifying, or optimizing around disclosure and detection controls.
