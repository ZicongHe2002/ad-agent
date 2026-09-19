from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.platforms.errors import (
    AuthorizationExpiredError,
    PlatformTemporaryError,
    PlatformTimeoutError,
    PublishUncertainError,
    RateLimitedError,
)
from app.platforms.mock import failure_injection
from app.platforms.mock.failure_injection import FailureInjector, MockFailureProfile
from app.platforms.mock.ranking import (
    VisibleRankingStrategy,
    chronological_comments,
    chronological_rank,
    visible_comments,
    visible_rank,
)


@dataclass
class Comment:
    id: str
    created_at: datetime
    like_count: int = 0
    author_pinned: bool = False
    external_comment_id: str | None = None


def _comments() -> list[object]:
    start = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)
    return [
        {
            "external_comment_id": "later",
            "created_at": start + timedelta(seconds=1),
            "like_count": 10,
            "author_pinned": False,
        },
        Comment("fallback", start, like_count=-3, author_pinned=False),
        Comment("unused", start, like_count=10, author_pinned=True, external_comment_id="pinned"),
    ]


def _ids(comments: list[object]) -> list[str]:
    result: list[str] = []
    for comment in comments:
        if isinstance(comment, dict):
            result.append(str(comment.get("external_comment_id") or comment.get("id")))
        else:
            result.append(str(comment.external_comment_id or comment.id))
    return result


def test_chronological_ranking_is_stable_for_dicts_and_objects() -> None:
    comments = _comments()
    assert _ids(chronological_comments(iter(comments))) == ["fallback", "pinned", "later"]
    assert chronological_rank(comments, "pinned") == 2
    with pytest.raises(KeyError, match="missing"):
        chronological_rank(comments, "missing")


def test_visible_ranking_strategies_and_one_based_rank() -> None:
    comments = _comments()
    assert _ids(visible_comments(comments, "chronological")) == [
        "fallback",
        "pinned",
        "later",
    ]
    assert _ids(visible_comments(comments, VisibleRankingStrategy.LIKES_WEIGHTED)) == [
        "pinned",
        "later",
        "fallback",
    ]
    assert _ids(visible_comments(comments, "author_pinned")) == [
        "pinned",
        "fallback",
        "later",
    ]
    assert visible_rank(comments, "later", "likes_weighted") == 2
    with pytest.raises(KeyError, match="missing"):
        visible_rank(comments, "missing", "chronological")
    with pytest.raises(ValueError):
        visible_comments(comments, "unsupported")


def test_personalized_ranking_is_seeded_and_viewer_specific() -> None:
    comments = _comments()
    baseline = _ids(
        visible_comments(
            comments,
            VisibleRankingStrategy.PERSONALIZED_RANDOM_SEEDED,
            seed=42,
            viewer_id="viewer-a",
        )
    )
    repeated = _ids(
        visible_comments(comments, "personalized_random_seeded", seed=42, viewer_id="viewer-a")
    )
    another_viewer = _ids(
        visible_comments(comments, "personalized_random_seeded", seed=42, viewer_id="viewer-c")
    )
    assert baseline == repeated
    assert another_viewer != baseline
    assert sorted(baseline) == ["fallback", "later", "pinned"]


def test_failure_profile_validates_bounds() -> None:
    with pytest.raises(ValidationError):
        MockFailureProfile(timeout_rate=1.01)
    with pytest.raises(ValidationError):
        MockFailureProfile(request_latency_ms=-1)


def test_failure_injector_configuration_reset_and_seeded_occurrence() -> None:
    profile = MockFailureProfile(seed=12, timeout_rate=0.5)
    first = FailureInjector(profile)
    second = FailureInjector(profile)
    assert [first.occurs(0.5) for _ in range(5)] == [second.occurs(0.5) for _ in range(5)]
    assert first.occurs(0.0) is False
    assert first.occurs(1.0) is True

    configured = MockFailureProfile(token_expired=True)
    assert first.configure(configured) is configured
    assert first.profile is configured
    first.reset()
    assert first.profile == MockFailureProfile()


@pytest.mark.asyncio
async def test_before_request_applies_latency_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(failure_injection.asyncio, "sleep", fake_sleep)
    injector = FailureInjector(MockFailureProfile(request_latency_ms=250))
    await injector.before_request("fetch", platform="MOCK")
    assert delays == [0.25]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "error_type", "expected_code"),
    [
        (
            MockFailureProfile(token_expired=True),
            AuthorizationExpiredError,
            "authorization_expired",
        ),
        (MockFailureProfile(http_429_rate=1), RateLimitedError, "rate_limited"),
        (MockFailureProfile(http_500_rate=1), PlatformTemporaryError, "platform_temporary_error"),
        (MockFailureProfile(timeout_rate=1), PlatformTimeoutError, "platform_timeout"),
    ],
)
async def test_before_request_injects_typed_failures(
    profile: MockFailureProfile,
    error_type: type[Exception],
    expected_code: str,
) -> None:
    with pytest.raises(error_type) as captured:
        await FailureInjector(profile).before_request("publish", platform="MOCK")
    error = captured.value
    assert error.code == expected_code
    assert error.platform == "MOCK"
    assert error.details["operation"] == "publish"


@pytest.mark.asyncio
async def test_rate_limit_failure_exposes_retry_after() -> None:
    profile = MockFailureProfile(http_429_rate=1, retry_after_seconds=3.5)
    with pytest.raises(RateLimitedError) as captured:
        await FailureInjector(profile).before_request("poll")
    assert captured.value.retry_after == 3.5


def test_after_publish_distinguishes_safe_and_uncertain_outcomes() -> None:
    FailureInjector().after_publish(idempotency_key="safe")

    injector = FailureInjector(MockFailureProfile(publish_success_but_timeout_rate=1))
    with pytest.raises(PublishUncertainError) as captured:
        injector.after_publish(idempotency_key="idem-1", platform="MOCK")
    assert captured.value.idempotency_key == "idem-1"
    assert captured.value.details == {"injected": True, "success_before_timeout": True}
