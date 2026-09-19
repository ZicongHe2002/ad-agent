from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedContent:
    title: str | None
    caption: str | None
    hashtags: list[str]
    mentions: list[str]
    ocr_text: str | None
    transcript: str | None
    visual_summary: str | None
    content_language: str
    content_hash: str
    data_completeness: float

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    result = _SPACE_RE.sub(" ", value).strip()
    return result or None


def normalize_content(post: Mapping[str, Any] | Any) -> NormalizedContent:
    def read(name: str, default: Any = None) -> Any:
        if isinstance(post, Mapping):
            return post.get(name, default)
        return getattr(post, name, default)

    title = normalize_text(read("title"))
    caption = normalize_text(read("caption"))
    ocr_text = normalize_text(read("ocr_text"))
    transcript = normalize_text(read("transcript"))
    visual_summary = normalize_text(read("visual_summary"))
    hashtags = sorted({str(x).strip().lstrip("#") for x in read("hashtags", []) if str(x).strip()})
    mentions = sorted({str(x).strip().lstrip("@") for x in read("mentions", []) if str(x).strip()})
    language = str(read("content_language", "zh-CN") or "zh-CN")

    present = sum(bool(x) for x in (title, caption, ocr_text, transcript, visual_summary))
    completeness = round(present / 5, 3)
    canonical = json.dumps(
        {
            "title": title,
            "caption": caption,
            "hashtags": hashtags,
            "mentions": mentions,
            "ocr_text": ocr_text,
            "transcript": transcript,
            "visual_summary": visual_summary,
            "content_language": language,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return NormalizedContent(
        title=title,
        caption=caption,
        hashtags=hashtags,
        mentions=mentions,
        ocr_text=ocr_text,
        transcript=transcript,
        visual_summary=visual_summary,
        content_language=language,
        content_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        data_completeness=completeness,
    )
