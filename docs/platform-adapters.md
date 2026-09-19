# Platform adapters

Every external integration implements one explicit contract and reports capability before invocation. A method must never infer support from a nearby operation: comment reply is not top-level comment publishing.

## Contract surface

Adapters expose capabilities and the supported subset of:

- latest-post discovery and post fetch;
- comment reading;
- top-level comment publishing;
- comment reply;
- publish reconciliation.

Unsupported calls raise a typed capability error. Authentication, rate limiting, temporary platform failure, permanent failure, uncertain publish, and policy block remain distinct error classes.

## Invocation rules

1. Load the current capability record for the exact platform and operation.
2. Verify account scope and authorization conditions.
3. Acquire the platform/account rate-limit token.
4. Send a request with timeout, trace ID, and idempotency metadata where supported.
5. Persist a sanitized receipt or typed failure.
6. On an ambiguous timeout, reconcile before retrying.

Adapters may not fall back to browser automation, private endpoints, alternate accounts, or hidden scraping. An OPEN circuit breaker delays work; it does not select an undeclared path.

## Documentation requirement

Each real adapter owns a `CAPABILITIES.md` recording operation, status, evidence source, account/application scope, conditions, owner, verified date, and expiry. The root [PLATFORM_CAPABILITIES.md](../PLATFORM_CAPABILITIES.md) is the cross-platform summary.
