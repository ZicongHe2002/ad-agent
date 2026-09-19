from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.capability_service import verify_capability_record
from app.services.comment_service import normalize_comment
from app.services.metrics_service import ranking_summary
from app.services.monitor_service import PollingContext, deterministic_jitter, next_poll_interval
from app.services.opportunity_service import compute_opportunity_score, opportunity_band
from app.services.publish_service import build_idempotency_key, route_publish
from app.services.quality_service import decide_quality
from app.services.risk_service import evaluate_hard_risk


def test_jitter_is_deterministic_and_bounded() -> None:
    first = deterministic_jitter("creator-1", "2026-09-02T10")
    second = deterministic_jitter("creator-1", "2026-09-02T10")
    assert first == second
    assert 0.85 <= first < 1.15


@pytest.mark.parametrize(
    ("context", "minimum", "maximum"),
    [
        (PollingContext("a", capability_status="SUPPORTED", current_hour="h"), 500, 700),
        (
            PollingContext(
                "a",
                capability_status="SUPPORTED",
                priority=95,
                in_high_probability_window=True,
                current_hour="h",
            ),
            8,
            12,
        ),
        (PollingContext("a", capability_status="UNKNOWN", current_hour="h"), 3600, 3600),
    ],
)
def test_poll_intervals(context: PollingContext, minimum: int, maximum: int) -> None:
    assert minimum <= next_poll_interval(context) <= maximum


def test_opportunity_score_is_server_computed_and_clamped() -> None:
    values = {
        name: 100
        for name in (
            "creator_value",
            "relevance",
            "audience_match",
            "traffic_potential",
            "post_velocity",
            "brand_fit",
        )
    }
    values.update(commercial_risk=0, platform_risk=0)
    score = compute_opportunity_score(values, "OWN_ACCOUNT")
    assert score == 99
    assert opportunity_band(score) == "HIGH_PRIORITY_CANDIDATE"
    assert compute_opportunity_score(values, "COMPETITOR") == 0


def test_comment_normalization() -> None:
    assert normalize_comment("  好 好 看！") == "好好看"
    assert normalize_comment("ＡＢＣ") == "abc"


def test_quality_hard_failure_blocks() -> None:
    result = decide_quality(
        {
            "anchor_coverage": 1,
            "specificity": 1,
            "fluency": 1,
            "voice_match": 1,
            "novelty": 1,
            "truthfulness": 1,
            "fake_experience_detected": True,
        }
    )
    assert result.decision == "BLOCK"


def test_hard_risk_fails_closed() -> None:
    result = evaluate_hard_risk({"critical_dependencies_available": False})
    assert result.decision == "BLOCK"
    assert "FAIL_CLOSED" in result.matched_rules


def test_publish_routes_every_capability_state() -> None:
    assert route_publish("SUPPORTED").mode == "OFFICIAL_API"
    assert route_publish("CONDITIONAL").mode == "MANUAL"
    assert (
        route_publish("CONDITIONAL", authorization_satisfies_conditions=True).mode == "OFFICIAL_API"
    )
    assert route_publish("AUTH_REQUIRED").mode == "MANUAL"
    assert route_publish("MANUAL").mode == "MANUAL"
    assert route_publish("UNKNOWN").mode == "MANUAL"
    assert route_publish("UNSUPPORTED").mode == "UNSUPPORTED"
    assert route_publish("RATE_LIMITED").mode == "DEFERRED"
    assert route_publish("DISABLED").mode == "BLOCKED"


def test_idempotency_key_is_stable_and_scoped() -> None:
    kwargs = dict(
        tenant_id="default",
        platform="MOCK",
        brand_account_id="account",
        external_post_id="post",
        campaign_id="campaign",
    )
    assert build_idempotency_key(**kwargs) == build_idempotency_key(**kwargs)
    assert build_idempotency_key(**kwargs) != build_idempotency_key(
        **{**kwargs, "campaign_id": "other"}
    )


def test_unknown_rank_is_excluded_from_denominator() -> None:
    result = ranking_summary([1, 4, 6, None])
    assert result["measured"] == 3
    assert result["measurement_coverage"] == 0.75
    assert result["first_comment_success_rate"] == pytest.approx(1 / 3)
    assert result["top5_success_rate"] == pytest.approx(2 / 3)


def test_capability_scope_and_expiry_are_enforced() -> None:
    now = datetime.now(timezone.utc)
    record = {
        "status": "CONDITIONAL",
        "expires_at": now + timedelta(days=1),
        "scope": {
            "account_types": ["BRAND_OFFICIAL"],
            "target_content_types": ["VIDEO"],
            "authorization_required": True,
        },
    }
    assert verify_capability_record(
        record,
        account_type="BRAND_OFFICIAL",
        target_content_type="VIDEO",
        has_authorization=True,
        now=now,
    ).allowed
    assert not verify_capability_record(
        record,
        account_type="HUMAN_OPERATOR",
        target_content_type="VIDEO",
        has_authorization=True,
        now=now,
    ).allowed
    expired = {**record, "expires_at": now - timedelta(seconds=1)}
    assert verify_capability_record(expired, now=now).status == "UNKNOWN"
