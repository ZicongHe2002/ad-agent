from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from hashlib import sha256

_PUNCT_RE = re.compile(r"[^\w\u3400-\u9fff]+", re.UNICODE)


def normalize_comment(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    return _PUNCT_RE.sub("", text)


def comment_intent_key(text: str) -> str:
    return sha256(normalize_comment(text).encode("utf-8")).hexdigest()[:24]


def merge_recent_comments(*groups: Iterable[str], limit: int = 220) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for text in group:
            normalized = normalize_comment(text)
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(text)
                if len(merged) >= limit:
                    return merged
    return merged
