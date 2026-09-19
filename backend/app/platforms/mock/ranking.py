"""Deterministic comment-ranking strategies for the mock platform."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Any


class VisibleRankingStrategy(str, Enum):
    CHRONOLOGICAL = "CHRONOLOGICAL"
    LIKES_WEIGHTED = "LIKES_WEIGHTED"
    AUTHOR_PINNED = "AUTHOR_PINNED"
    PERSONALIZED_RANDOM_SEEDED = "PERSONALIZED_RANDOM_SEEDED"


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _comment_id(item: Any) -> str:
    value = _value(item, "external_comment_id", None)
    if value is None:
        value = _value(item, "id", "")
    return str(value)


def chronological_comments(comments: Iterable[Any]) -> list[Any]:
    return sorted(
        comments,
        key=lambda item: (_value(item, "created_at"), _comment_id(item)),
    )


def chronological_rank(comments: Sequence[Any], comment_id: Any) -> int:
    """Return a one-based rank, using the specification's stable tie breaker."""

    wanted = str(comment_id)
    for index, item in enumerate(chronological_comments(comments), start=1):
        if _comment_id(item) == wanted:
            return index
    raise KeyError(f"Comment {wanted} was not found")


def _personalized_score(comment: Any, *, seed: str, viewer_id: str) -> bytes:
    material = f"{seed}\x1f{viewer_id}\x1f{_comment_id(comment)}".encode()
    return hashlib.sha256(material).digest()


def visible_comments(
    comments: Iterable[Any],
    strategy: VisibleRankingStrategy | str,
    *,
    seed: str | int = 0,
    viewer_id: str = "default",
) -> list[Any]:
    mode = (
        strategy
        if isinstance(strategy, VisibleRankingStrategy)
        else VisibleRankingStrategy(str(strategy).upper())
    )
    source = list(comments)
    if mode == VisibleRankingStrategy.CHRONOLOGICAL:
        return chronological_comments(source)
    if mode == VisibleRankingStrategy.LIKES_WEIGHTED:
        return sorted(
            source,
            key=lambda item: (
                -max(0, int(_value(item, "like_count", 0))),
                _value(item, "created_at"),
                _comment_id(item),
            ),
        )
    if mode == VisibleRankingStrategy.AUTHOR_PINNED:
        return sorted(
            source,
            key=lambda item: (
                not bool(_value(item, "author_pinned", False)),
                _value(item, "created_at"),
                _comment_id(item),
            ),
        )
    return sorted(
        source,
        key=lambda item: (
            _personalized_score(item, seed=str(seed), viewer_id=viewer_id),
            _comment_id(item),
        ),
    )


def visible_rank(
    comments: Sequence[Any],
    comment_id: Any,
    strategy: VisibleRankingStrategy | str,
    *,
    seed: str | int = 0,
    viewer_id: str = "default",
) -> int:
    wanted = str(comment_id)
    for index, item in enumerate(
        visible_comments(comments, strategy, seed=seed, viewer_id=viewer_id),
        start=1,
    ):
        if _comment_id(item) == wanted:
            return index
    raise KeyError(f"Comment {wanted} was not found")


__all__ = [
    "VisibleRankingStrategy",
    "chronological_comments",
    "chronological_rank",
    "visible_comments",
    "visible_rank",
]
