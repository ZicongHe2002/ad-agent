from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

from app.services.comment_service import normalize_comment

FAKE_EXPERIENCE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"我(买|用|穿|吃|喝|试)(过|了)",
        r"作为(一个)?(普通)?消费者",
        r"亲测",
        r"回购",
        r"my (purchase|experience|order)",
        r"i (bought|used|tried)",
    )
)


def normalized_edit_distance(original: str, final: str) -> float:
    return round(
        1.0 - SequenceMatcher(None, normalize_comment(original), normalize_comment(final)).ratio(),
        4,
    )


def validate_review_text(
    text: str,
    *,
    anchors: Iterable[str],
    forbidden_phrases: Iterable[str] = (),
    brand_official: bool = False,
) -> list[str]:
    """Re-run immutable hard gates after every human edit.

    A reviewer may resolve semantic uncertainty, but cannot override identity,
    truthfulness, approved-claim, or policy gates.
    """

    errors: list[str] = []
    stripped = text.strip()
    if not stripped:
        errors.append("EMPTY_COMMENT")
    if not any(anchor and anchor in stripped for anchor in anchors):
        errors.append("MISSING_CONCRETE_ANCHOR")
    if any(phrase and phrase.casefold() in stripped.casefold() for phrase in forbidden_phrases):
        errors.append("FORBIDDEN_PHRASE")
    if brand_official and any(pattern.search(stripped) for pattern in FAKE_EXPERIENCE_PATTERNS):
        errors.append("FAKE_CONSUMER_EXPERIENCE")
    if re.search(r"(?:微信|vx|v信|加我|私聊|手机号|https?://)", stripped, re.IGNORECASE):
        errors.append("OFF_PLATFORM_CONTACT")
    return errors
