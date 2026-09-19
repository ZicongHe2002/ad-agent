# Capability policy

The root [PLATFORM_CAPABILITIES.md](../PLATFORM_CAPABILITIES.md) is the authoritative repository matrix. This document explains how runtime code and the operator console consume it.

## Status meanings

- `SUPPORTED`: current evidence confirms the exact operation and scope.
- `CONDITIONAL`: supported only when recorded conditions are satisfied.
- `AUTH_REQUIRED`: the capability may exist, but the selected account lacks verified authorization.
- `MANUAL`: the product provides a human-assisted workflow only.
- `UNSUPPORTED`: authoritative evidence says the operation is unavailable.
- `UNKNOWN`: evidence is missing, ambiguous, stale, or scope-inapplicable.
- `RATE_LIMITED`: temporarily deferred under platform quota pressure.
- `DISABLED`: an administrator or circuit breaker has disabled invocation.

`UNKNOWN` and `UNSUPPORTED` are never executable automatic routes. `comment_reply` never implies `top_level_comment`.

## Evidence record

Each operation record includes:

```text
platform · operation · status · source URL/document
application/account scope · authorization conditions
verified_at · expires_at · owner · notes
```

Expired evidence disables auto-publish until reverified. Runtime requests store the capability snapshot used for the decision, making later audits independent of subsequent matrix changes.

## Initial posture

- Mock Platform capabilities needed by automated tests are supported.
- Real-platform third-party top-level comment publishing remains UNKNOWN unless current official evidence and granted account scope prove otherwise.
- Where automatic capability is not verified, route to a clearly labeled manual workflow or block; do not synthesize an endpoint or silently fall back to browser interaction. A separate browser channel is under research and has no verified publishing capability yet; see [the research note](browser-publishing-research-2026-09-19.md).
