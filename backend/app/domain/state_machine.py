from __future__ import annotations

from typing import Protocol

from app.core.exceptions import InvalidStateTransition

from .enums import CommentJobState

ALLOWED_TRANSITIONS: dict[CommentJobState, frozenset[CommentJobState]] = {
    CommentJobState.DISCOVERED: frozenset(
        {CommentJobState.FETCHING, CommentJobState.SKIPPED, CommentJobState.BLOCKED}
    ),
    CommentJobState.FETCHING: frozenset(
        {CommentJobState.ANALYZING, CommentJobState.FAILED, CommentJobState.SKIPPED}
    ),
    CommentJobState.ANALYZING: frozenset(
        {
            CommentJobState.GENERATING,
            CommentJobState.SKIPPED,
            CommentJobState.BLOCKED,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.GENERATING: frozenset(
        {CommentJobState.QUALITY_CHECKING, CommentJobState.FAILED}
    ),
    CommentJobState.QUALITY_CHECKING: frozenset(
        {
            CommentJobState.GENERATING,
            CommentJobState.RISK_CHECKING,
            CommentJobState.WAITING_REVIEW,
            CommentJobState.BLOCKED,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.RISK_CHECKING: frozenset(
        {
            CommentJobState.WAITING_REVIEW,
            CommentJobState.READY,
            CommentJobState.SKIPPED,
            CommentJobState.BLOCKED,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.WAITING_REVIEW: frozenset(
        {CommentJobState.READY, CommentJobState.SKIPPED, CommentJobState.BLOCKED}
    ),
    CommentJobState.READY: frozenset(
        {
            CommentJobState.PUBLISHING,
            CommentJobState.WAITING_MANUAL_PUBLISH,
            CommentJobState.READY_FOR_RETRY,
            CommentJobState.BLOCKED,
        }
    ),
    CommentJobState.WAITING_MANUAL_PUBLISH: frozenset(
        {
            CommentJobState.PUBLISHING,
            CommentJobState.PUBLISHED,
            CommentJobState.SKIPPED,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.PUBLISHING: frozenset(
        {
            CommentJobState.PUBLISHED,
            CommentJobState.PUBLISH_UNCERTAIN,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.PUBLISH_UNCERTAIN: frozenset(
        {
            CommentJobState.PUBLISHED,
            CommentJobState.READY_FOR_RETRY,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.READY_FOR_RETRY: frozenset(
        {
            CommentJobState.PUBLISHING,
            CommentJobState.WAITING_MANUAL_PUBLISH,
            CommentJobState.BLOCKED,
            CommentJobState.FAILED,
        }
    ),
    CommentJobState.PUBLISHED: frozenset(),
    CommentJobState.SKIPPED: frozenset(),
    CommentJobState.BLOCKED: frozenset(),
    CommentJobState.FAILED: frozenset(),
}

TERMINAL_STATES = frozenset(
    {
        CommentJobState.PUBLISHED,
        CommentJobState.SKIPPED,
        CommentJobState.BLOCKED,
        CommentJobState.FAILED,
    }
)


class StatefulCommentJob(Protocol):
    state: CommentJobState
    state_reason: str | None


def can_transition(source: CommentJobState, target: CommentJobState) -> bool:
    return target in ALLOWED_TRANSITIONS[source]


def transition(job: StatefulCommentJob, target: CommentJobState, reason: str) -> None:
    if not reason.strip():
        raise ValueError("state transition reason must be non-empty")
    if not can_transition(job.state, target):
        raise InvalidStateTransition(job.state, target)
    job.state = target
    job.state_reason = reason.strip()
    if hasattr(job, "state_version"):
        job.state_version += 1
