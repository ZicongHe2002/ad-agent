from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain import scoring
from app.domain.enums import CapabilityStatus, CreatorRelationship, Platform, PublishMode
from app.domain.scoring import PollingContext, deterministic_jitter, next_poll_interval
from app.domain.value_objects import AuthorizationScope, CapabilityEvidence, PublishRoute


def _opportunity_parts(value: float = 100.0) -> dict[str, float]:
    return {
        "creator_value": value,
        "relevance": value,
        "audience_match": value,
        "traffic_potential": value,
        "post_velocity": value,
        "brand_fit": value,
        "commercial_risk": 0.0,
        "platform_risk": 0.0,
    }


def test_domain_opportunity_score_weights_relationships_and_clamps() -> None:
    assert scoring.opportunity_score(**_opportunity_parts()) == 90.0
    assert (
        scoring.opportunity_score(
            **_opportunity_parts(),
            relationship=CreatorRelationship.OWN_ACCOUNT,
        )
        == 99.0
    )
    assert (
        scoring.opportunity_score(
            **_opportunity_parts(),
            relationship=CreatorRelationship.COMPETITOR,
        )
        == 0.0
    )
    risky = {**_opportunity_parts(0), "commercial_risk": 100.0, "platform_risk": 100.0}
    assert scoring.opportunity_score(**risky) == 0.0


@pytest.mark.parametrize(("field", "value"), [("relevance", -0.01), ("brand_fit", 100.01)])
def test_domain_opportunity_score_rejects_out_of_range_parts(field: str, value: float) -> None:
    parts = {**_opportunity_parts(), field: value}
    with pytest.raises(ValueError, match="between 0 and 100"):
        scoring.opportunity_score(**parts)


def test_domain_jitter_is_hourly_timezone_normalized_and_bounded() -> None:
    utc_hour = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)
    offset_hour = utc_hour.astimezone(timezone(timedelta(hours=-4)))
    first = deterministic_jitter("creator", utc_hour)

    assert first == deterministic_jitter("creator", offset_hour)
    assert 0.85 <= first < 1.15
    assert first != deterministic_jitter("other-creator", utc_hour)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"monitor_paused": True}, 3600),
        ({"capability_status": CapabilityStatus.UNKNOWN}, 3600),
        ({"auth_invalid": True}, 1800),
        ({}, 600),
        ({"in_expected_publish_window": True}, 60),
        ({"priority": 90, "in_high_probability_window": True}, 10),
        ({"recent_activity_score": 0.8}, 60),
        ({"failure_count": 6}, 960),
        ({"platform_rate_limit_pressure": 0.8}, 1500),
        ({"normal_interval_sec": 1}, 5),
        ({"normal_interval_sec": 3600, "platform_rate_limit_pressure": 1.0}, 3600),
    ],
)
def test_domain_next_poll_interval_policy(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    expected: int,
) -> None:
    monkeypatch.setattr(scoring, "deterministic_jitter", lambda *_args, **_kwargs: 1.0)
    defaults: dict[str, object] = {
        "creator_platform_account_id": "creator",
        "capability_status": CapabilityStatus.SUPPORTED,
    }
    assert next_poll_interval(PollingContext(**{**defaults, **overrides})) == expected


def test_domain_poll_interval_combines_hot_activity_backoff_and_pressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scoring, "deterministic_jitter", lambda *_args, **_kwargs: 1.0)
    context = PollingContext(
        creator_platform_account_id="creator",
        capability_status=CapabilityStatus.CONDITIONAL,
        priority=95,
        in_expected_publish_window=True,
        in_high_probability_window=True,
        recent_activity_score=1.0,
        failure_count=3,
        platform_rate_limit_pressure=0.9,
    )
    assert next_poll_interval(context) == 300


def test_capability_evidence_requires_aware_dates_and_is_frozen() -> None:
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    evidence = CapabilityEvidence(
        source_title="Official API reference",
        source_owner="Platform",
        source_url="https://example.test/docs",
        verified_at=now,
        expires_at=now + timedelta(days=30),
        verified_by_user_id=uuid4(),
    )
    assert evidence.verified_at == now

    with pytest.raises(ValidationError, match="timezone-aware"):
        CapabilityEvidence(
            source_title="Reference",
            source_owner="Platform",
            verified_at=datetime(2026, 9, 4),
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        CapabilityEvidence(
            source_title="Reference",
            source_owner="Platform",
            verified_at=now,
            expires_at=datetime(2026, 10, 4),
        )
    with pytest.raises(ValidationError):
        evidence.source_title = "Changed"


def test_capability_evidence_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CapabilityEvidence(
            source_title="Reference",
            source_owner="Platform",
            verified_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
            unexpected=True,
        )


def test_authorization_scope_defaults_allows_extension_and_is_frozen() -> None:
    scope = AuthorizationScope(vendor_condition="approved")
    assert scope.scopes == []
    assert scope.account_types == []
    assert scope.target_content_types == []
    assert scope.authorization_required is True
    assert scope.model_extra == {"vendor_condition": "approved"}

    with pytest.raises(ValidationError):
        scope.scopes = ["comment.write"]


def test_publish_route_validates_enums_and_forbids_extensions() -> None:
    route = PublishRoute(
        platform=Platform.MOCK,
        mode=PublishMode.OFFICIAL_API,
        capability_status=CapabilityStatus.SUPPORTED,
        permitted=True,
        reason="Capability verified",
        metadata={"scope": "comment.write"},
    )
    assert route.metadata["scope"] == "comment.write"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        PublishRoute(
            platform=Platform.MOCK,
            mode=PublishMode.MANUAL,
            capability_status=CapabilityStatus.MANUAL,
            permitted=True,
            reason="Manual handoff",
            unexpected=True,
        )
