from __future__ import annotations

import pytest

from app.services import monitor_service
from app.services.metrics_service import latency_summary, percentile, ranking_summary
from app.services.monitor_service import (
    InMemoryTokenBucket,
    PollingContext,
    RedisPlatformTokenBucket,
    RedisPollFailureTracker,
    RedisPollLock,
    next_poll_interval,
)
from app.services.quality_service import decide_quality, quality_score
from app.services.risk_service import RiskPolicyResult, combine_risk, evaluate_hard_risk


def test_service_jitter_is_deterministic_bounded_and_entity_specific() -> None:
    first = monitor_service.deterministic_jitter("creator-a", "2026-09-04T10")
    assert first == monitor_service.deterministic_jitter("creator-a", "2026-09-04T10")
    assert first != monitor_service.deterministic_jitter("creator-b", "2026-09-04T10")
    assert 0.85 <= first < 1.15


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"monitor_paused": True}, 3600),
        ({"capability_status": "UNKNOWN"}, 3600),
        ({"auth_invalid": True}, 1800),
        ({}, 600),
        ({"in_expected_publish_window": True}, 60),
        ({"priority": 95, "in_high_probability_window": True}, 10),
        ({"recent_activity_score": 0.8}, 60),
        ({"failure_count": 6}, 960),
        ({"failure_count": 100}, 3600),
        ({"platform_rate_limit_pressure": 0.8}, 1500),
        ({"normal_interval_sec": 1}, 5),
        ({"normal_interval_sec": 3600, "platform_rate_limit_pressure": 1.0}, 3600),
    ],
)
def test_service_next_poll_interval_policy(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    expected: int,
) -> None:
    monkeypatch.setattr(monitor_service, "deterministic_jitter", lambda *_args: 1.0)
    defaults: dict[str, object] = {
        "creator_platform_account_id": "creator",
        "capability_status": "SUPPORTED",
    }
    assert next_poll_interval(PollingContext(**{**defaults, **overrides})) == expected


def test_service_poll_interval_combines_all_dynamic_reducers_and_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monitor_service, "deterministic_jitter", lambda *_args: 1.0)
    context = PollingContext(
        creator_platform_account_id="creator",
        capability_status="AUTH_REQUIRED",
        priority=99,
        in_expected_publish_window=True,
        in_high_probability_window=True,
        recent_activity_score=1.0,
        failure_count=3,
        platform_rate_limit_pressure=0.9,
    )
    assert next_poll_interval(context) == 300


def test_token_bucket_refills_caps_and_rejects_when_insufficient() -> None:
    bucket = InMemoryTokenBucket(capacity=2, refill_per_second=0.5)

    assert bucket.acquire(now=0, amount=1.5)
    assert not bucket.acquire(now=0, amount=1)
    assert bucket.acquire(now=2, amount=1)
    assert not bucket.acquire(now=1, amount=1)
    assert bucket.acquire(now=100, amount=2)
    assert bucket.tokens == 0


class FakeRedis:
    def __init__(self) -> None:
        self.eval_result: list[object] | int = [1, b"4.5", b"0"]
        self.get_result: object | None = None
        self.incr_result = 1
        self.set_result: object = True
        self.calls: list[tuple[object, ...]] = []

    async def eval(self, *args: object) -> list[object] | int:
        self.calls.append(("eval", *args))
        return self.eval_result

    async def set(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("set", *args, kwargs))
        return self.set_result

    async def get(self, key: str) -> object | None:
        self.calls.append(("get", key))
        return self.get_result

    async def incr(self, key: str) -> int:
        self.calls.append(("incr", key))
        return self.incr_result

    async def expire(self, key: str, ttl: int) -> None:
        self.calls.append(("expire", key, ttl))

    async def delete(self, key: str) -> None:
        self.calls.append(("delete", key))


@pytest.mark.parametrize(
    ("capacity", "refill", "message"),
    [(0, 1, "capacity must be positive"), (1, -0.1, "cannot be negative")],
)
def test_redis_token_bucket_rejects_invalid_configuration(
    capacity: float,
    refill: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RedisPlatformTokenBucket(FakeRedis(), "MOCK", capacity=capacity, refill_per_second=refill)


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, -1, 11])
async def test_redis_token_bucket_rejects_invalid_amount(amount: float) -> None:
    bucket = RedisPlatformTokenBucket(FakeRedis(), "MOCK")
    with pytest.raises(ValueError, match="amount must be positive"):
        await bucket.acquire(amount=amount)


@pytest.mark.asyncio
async def test_redis_token_bucket_returns_atomic_allowed_decision() -> None:
    redis = FakeRedis()
    redis.eval_result = [1, b"-0.5", "9.2"]
    bucket = RedisPlatformTokenBucket(redis, "MOCK", capacity=5, refill_per_second=0.5)

    decision = await bucket.acquire(now=100.25, amount=1.5)

    assert decision.allowed is True
    assert decision.remaining_tokens == 0
    assert decision.retry_after_seconds == 0
    call = redis.calls[0]
    assert call[0] == "eval"
    assert call[3:] == ("poll_token_bucket:MOCK", 100.25, 5.0, 0.5, 1.5, 60)


@pytest.mark.asyncio
async def test_redis_token_bucket_computes_retry_and_zero_refill_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    redis.eval_result = [0, "0.25", b"0.1"]
    monkeypatch.setattr(monitor_service.time, "time", lambda: 123.0)
    bucket = RedisPlatformTokenBucket(redis, "DOUYIN", capacity=2, refill_per_second=0)

    decision = await bucket.acquire()

    assert decision.allowed is False
    assert decision.remaining_tokens == 0.25
    assert decision.retry_after_seconds == 1
    assert redis.calls[0][-1] == 7200


@pytest.mark.asyncio
async def test_redis_poll_lock_uses_owner_token_and_safe_release() -> None:
    redis = FakeRedis()
    lock = RedisPollLock(redis, "creator-1", expected_request_timeout_seconds=15)

    assert lock.key == "poll_lock:creator-1"
    assert lock.ttl_seconds == 30
    assert await lock.release() is False
    assert await lock.acquire() is True
    assert redis.calls[0] == (
        "set",
        lock.key,
        lock.token,
        {"nx": True, "ex": 30},
    )
    assert await lock.release() is True
    assert lock.acquired is False
    assert redis.calls[1][1:] == (
        monitor_service.RELEASE_POLL_LOCK_SCRIPT,
        1,
        lock.key,
        lock.token,
    )


@pytest.mark.asyncio
async def test_redis_poll_lock_reports_contention_and_failed_release() -> None:
    redis = FakeRedis()
    redis.set_result = None
    lock = RedisPollLock(redis, "creator-2", expected_request_timeout_seconds=15.1)
    assert lock.ttl_seconds == 31
    assert await lock.acquire() is False

    lock.acquired = True
    redis.eval_result = 0
    assert await lock.release() is False


@pytest.mark.asyncio
async def test_redis_poll_failure_tracker_lifecycle_and_decoding() -> None:
    redis = FakeRedis()
    tracker = RedisPollFailureTracker(redis, "creator-3")

    assert await tracker.current() == 0
    redis.get_result = b"-2"
    assert await tracker.current() == 0
    redis.get_result = "4"
    assert await tracker.current() == 4

    redis.incr_result = 5
    assert await tracker.record_failure() == 5
    assert ("expire", tracker.key, 86_400) in redis.calls
    await tracker.reset()
    assert redis.calls[-1] == ("delete", tracker.key)


def test_percentile_handles_empty_exact_and_interpolated_samples() -> None:
    assert percentile([], 0.5) is None
    assert percentile([9], 0.99) == 9
    assert percentile([40, 10, 30, 20], 0.5) == 25
    assert percentile([0, 100], 0.9) == 90


def test_latency_summary_materializes_generator_and_reports_percentiles() -> None:
    summary = latency_summary(value for value in [4.0, 1.0, 2.0, 3.0])
    assert summary == {
        "count": 4,
        "p50": 2.5,
        "p90": 3.7,
        "p95": 3.8499999999999996,
        "p99": 3.9699999999999998,
    }
    assert latency_summary([]) == {
        "count": 0,
        "p50": None,
        "p90": None,
        "p95": None,
        "p99": None,
    }


def test_ranking_summary_handles_empty_unknown_and_measured_ranks() -> None:
    assert ranking_summary([]) == {
        "samples": 0,
        "measured": 0,
        "measurement_coverage": 0.0,
        "first_comment_success_rate": 0.0,
        "top5_success_rate": 0.0,
    }
    assert ranking_summary([None, None]) == {
        "samples": 2,
        "measured": 0,
        "measurement_coverage": 0.0,
        "first_comment_success_rate": 0.0,
        "top5_success_rate": 0.0,
    }
    measured = ranking_summary(rank for rank in [1, 5, 6, None])
    assert measured["measurement_coverage"] == 0.75
    assert measured["first_comment_success_rate"] == pytest.approx(1 / 3)
    assert measured["top5_success_rate"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("relationship", ["COMPETITOR", "BLOCKED_CREATOR"])
def test_hard_risk_blocks_prohibited_creator_relationships(relationship: str) -> None:
    result = evaluate_hard_risk({"creator_relationship": relationship})
    assert result == RiskPolicyResult("BLOCK", 1.0, ("CREATOR_BLOCKED",))


def test_hard_risk_collects_every_matching_gate_in_stable_order() -> None:
    context = {
        "fake_experience": True,
        "fake_identity": True,
        "unapproved_claim": True,
        "external_contact": True,
        "prohibited_phrase": True,
        "daily_limit_exceeded": True,
        "creator_limit_exceeded": True,
        "duplicate_intent": True,
        "kill_switch": True,
        "disclosure_unresolved": True,
        "policy_expired": True,
    }
    assert evaluate_hard_risk(context).matched_rules == (
        "FAKE_EXPERIENCE",
        "FAKE_IDENTITY",
        "UNAPPROVED_CLAIM",
        "EXTERNAL_CONTACT",
        "PROHIBITED_PHRASE",
        "DAILY_LIMIT",
        "CREATOR_DAILY_LIMIT",
        "DUPLICATE_INTENT",
        "KILL_SWITCH",
        "DISCLOSURE_UNRESOLVED",
        "POLICY_EXPIRED",
    )


def test_hard_risk_allows_safe_context_and_fails_closed() -> None:
    assert evaluate_hard_risk({}) == RiskPolicyResult("ALLOW", 0.0, ())
    assert evaluate_hard_risk({"critical_dependencies_available": False}) == RiskPolicyResult(
        "BLOCK", 1.0, ("FAIL_CLOSED",)
    )


@pytest.mark.parametrize(
    ("semantic_score", "expected"),
    [
        (None, RiskPolicyResult("ALLOW", 0.0, ())),
        (-1, RiskPolicyResult("ALLOW", 0.0, ())),
        (0.29, RiskPolicyResult("ALLOW", 0.29, ())),
        (0.30, RiskPolicyResult("REVIEW", 0.30, ("SEMANTIC_UNCERTAINTY",))),
        (0.65, RiskPolicyResult("REVIEW", 0.65, ("SEMANTIC_UNCERTAINTY",))),
        (0.66, RiskPolicyResult("BLOCK", 0.66, ("SEMANTIC_RISK",))),
        (2, RiskPolicyResult("BLOCK", 1.0, ("SEMANTIC_RISK",))),
    ],
)
def test_combine_risk_applies_semantic_thresholds(
    semantic_score: float | None,
    expected: RiskPolicyResult,
) -> None:
    assert combine_risk(RiskPolicyResult("ALLOW", 0.0, ()), semantic_score) == expected


def test_combine_risk_never_overrides_hard_block() -> None:
    block = RiskPolicyResult("BLOCK", 1.0, ("HARD_RULE",))
    assert combine_risk(block, 0.0) is block


def _quality_values(score: object, **overrides: object) -> dict[str, object]:
    return {
        "anchor_coverage": score,
        "specificity": score,
        "fluency": score,
        "voice_match": score,
        "novelty": score,
        "truthfulness": score,
        **overrides,
    }


def test_quality_score_applies_weights_rounding_and_clamps() -> None:
    assert (
        quality_score(
            {
                field: 1
                for field in (
                    "anchor_coverage",
                    "specificity",
                    "fluency",
                    "voice_match",
                    "novelty",
                    "truthfulness",
                )
            }
        )
        == 1.0
    )
    assert quality_score({"anchor_coverage": 10}) == 1.0
    assert quality_score({"anchor_coverage": -10}) == 0.0
    assert quality_score({"anchor_coverage": 0.33333}) == 0.0833


def test_quality_hard_failures_take_precedence_and_collect_reasons() -> None:
    result = decide_quality(
        _quality_values(
            1,
            fake_experience_detected=True,
            fake_identity_detected=True,
            unsupported_claim_detected=True,
            duplicate_similarity_max=1,
        )
    )
    assert result.decision == "BLOCK"
    assert result.score == 1
    assert result.reasons == (
        "FAKE_EXPERIENCE_DETECTED",
        "FAKE_IDENTITY_DETECTED",
        "UNSUPPORTED_CLAIM_DETECTED",
    )


@pytest.mark.parametrize(
    ("values", "decision", "reason"),
    [
        (_quality_values(1, duplicate_similarity_max=0.90), "BLOCK", "DUPLICATE"),
        (_quality_values(1, duplicate_similarity_max=0.82), "REVIEW", "NEAR_DUPLICATE"),
        (_quality_values("0.80"), "ALLOW", None),
        (_quality_values(0.65), "REVIEW", "QUALITY_REVIEW"),
        (_quality_values(0.649), "REGENERATE", "QUALITY_TOO_LOW"),
        (_quality_values(object()), "REGENERATE", "QUALITY_TOO_LOW"),
        (_quality_values("not-a-number"), "REGENERATE", "QUALITY_TOO_LOW"),
    ],
)
def test_decide_quality_thresholds_and_input_coercion(
    values: dict[str, object],
    decision: str,
    reason: str | None,
) -> None:
    result = decide_quality(values)
    assert result.decision == decision
    assert result.reasons == (() if reason is None else (reason,))


def test_decide_quality_treats_boolean_numeric_values_consistently() -> None:
    assert decide_quality(_quality_values(True)).decision == "ALLOW"
