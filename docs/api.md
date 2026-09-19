# API

All application endpoints are versioned under `/api/v1`. Errors use a stable envelope:

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

## Resource groups

- `/auth`: login and current user; refresh is used only when the backend issues a refresh token.
- `/brands`, `/products`, `/campaigns`: brand truth, claims, strategy, and limits.
- `/creators`: registry, monitoring, pause, and immediate poll requests.
- `/platform-accounts`: publishing identity, authorization verification, and account kill switch.
- `/posts`: content detail, analysis, and timeline.
- `/comments`: candidate and published comment views plus reconciliation.
- `/review/jobs`: claim, inspect, approve, edit-and-approve, and reject.
- `/metrics`: overview, latency, quality, and ranking with measurement coverage.
- `/system`: health, readiness, queues, capabilities, and privileged publisher controls.
- `/mock`: local platform creation and failure injection; disabled outside safe development/test environments.

## Authentication

Protected calls use `Authorization: Bearer <token>`. The browser API client performs one refresh attempt after a 401, clears invalid credentials, and surfaces the server trace ID through `ApiError`. Platform secrets are never returned to the browser.

## SSE

`GET /api/v1/events/stream` accepts creator, post, campaign, and event-type filters. It emits event IDs and heartbeats, accepts `Last-Event-ID`, and authorizes the same way as REST. Clients reconnect with bounded exponential backoff.
