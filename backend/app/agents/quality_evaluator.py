"""Deterministic authenticity, anti-spam, and quality checks."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from ..domain.enums import AccountKind, QualityDecision

_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
_GENERIC_ONLY = {
    "太棒了",
    "真棒",
    "好看",
    "绝了",
    "喜欢",
    "支持",
    "不错",
    "太赞了",
    "厉害",
    "爱了",
    "great",
    "awesome",
    "amazing",
    "love it",
    "nice",
    "beautiful",
    "so good",
}
_FAKE_EXPERIENCE_PATTERNS = (
    r"我(?:已经)?买(?:过|了)",
    r"我(?:一直)?用(?:过|了)",
    r"亲测",
    r"回购",
    r"用了\s*\d+\s*天",
    r"我家(?:人|孩子|宝宝|老公|老婆)",
    r"作为(?:一名|一个)?(?:妈妈|学生|医生|用户|消费者)",
    r"\bi (?:bought|purchased|use|used|tried|have been using)\b",
    r"\bmy (?:family|kids|husband|wife)\b",
)
_FAKE_IDENTITY_PATTERNS = (
    r"作为(?:一个|一名)?(?:普通)?(?:用户|消费者|路人|粉丝)",
    r"纯路人",
    r"不是广告",
    r"自来水",
    r"\bas (?:an? )?(?:ordinary )?(?:consumer|customer|user|fan)\b",
    r"\bnot an ad\b",
)
_CLAIM_PATTERNS = (
    r"100\s*%",
    r"百分之百",
    r"保证",
    r"永久",
    r"零风险",
    r"无副作用",
    r"治[疗愈]",
    r"根治",
    r"最(?:好|强|快|有效)",
    r"\b(?:guaranteed|cure[sd]?|risk[- ]free|best|fastest)\b",
)
_EXTERNAL_CONTACT_PATTERNS = (
    r"https?://",
    r"www\.",
    r"加(?:我)?微信",
    r"微信号",
    r"私信(?:我|领取|购买)",
    r"扫码",
    r"\b(?:whatsapp|telegram|wechat)\b",
    r"\b(?:dm|message) me\b",
)
_COMPETITOR_ATTACK_PATTERNS = (
    r"竞品.*(?:差|垃圾|不行|别买)",
    r"别家.*(?:差|垃圾|不行|别买)",
    r"\bcompetitor.*(?:bad|trash|inferior|avoid)\b",
)


def normalize_comment(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = _SPACE_RE.sub(" ", value).strip()
    return "".join(character for character in value if character.isalnum() or character.isspace())


def _ngrams(value: Sequence[str] | str, size: int) -> set[Any]:
    if not value:
        return set()
    if len(value) < size:
        return {tuple(value) if not isinstance(value, str) else value}
    return {
        tuple(value[index : index + size])
        if not isinstance(value, str)
        else value[index : index + size]
        for index in range(len(value) - size + 1)
    }


def jaccard(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def character_3gram_jaccard(left: str, right: str) -> float:
    return jaccard(
        _ngrams(normalize_comment(left).replace(" ", ""), 3),
        _ngrams(normalize_comment(right).replace(" ", ""), 3),
    )


def _word_tokens(text: str) -> list[str]:
    return _WORD_RE.findall(normalize_comment(text))


def word_2gram_jaccard(left: str, right: str) -> float:
    return jaccard(_ngrams(_word_tokens(left), 2), _ngrams(_word_tokens(right), 2))


def prefix_signature(text: str, length: int = 16) -> str:
    return normalize_comment(text).replace(" ", "")[:length]


def cta_signature(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    signatures = []
    categories = {
        "URL": r"https?://|www\.",
        "DIRECT_MESSAGE": r"私信|\bdm\b|message me",
        "WECHAT": r"微信|wechat",
        "BUY": r"购买|下单|buy now|shop now",
        "CONTACT": r"联系|contact|whatsapp|telegram",
    }
    for name, pattern in categories.items():
        if re.search(pattern, normalized):
            signatures.append(name)
    return tuple(signatures)


def comment_similarity(left: str, right: str) -> float:
    normalized_left = normalize_comment(left)
    normalized_right = normalize_comment(right)
    if normalized_left and normalized_left == normalized_right:
        return 1.0
    values = [
        character_3gram_jaccard(left, right),
        word_2gram_jaccard(left, right),
    ]
    left_prefix = prefix_signature(left)
    right_prefix = prefix_signature(right)
    if len(left_prefix) >= 6 and left_prefix == right_prefix:
        values.append(0.85)
    left_cta = cta_signature(left)
    if left_cta and left_cta == cta_signature(right):
        values.append(0.60)
    return round(max(values, default=0.0), 6)


def max_comment_similarity(comment: str, recent_comments: Sequence[str]) -> float:
    return max((comment_similarity(comment, existing) for existing in recent_comments), default=0.0)


def _data(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    return dict(vars(value)) if hasattr(value, "__dict__") else {}


def _text(candidate: Any) -> str:
    if isinstance(candidate, str):
        return candidate
    data = _data(candidate)
    return str(data.get("comment", data.get("text", "")))


def _matches_any(patterns: Sequence[str], text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text)
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def _claim_language_covered_by_approved_text(
    text: str,
    approved_claim_texts: Sequence[str],
) -> bool:
    """Require every risky assertion token to live inside an approved claim.

    Merely mentioning an unrelated approved fact must never authorize the rest
    of a sentence.  We deliberately use exact, normalized spans here rather
    than fuzzy/semantic matching: uncertainty about claim coverage fails closed.
    """

    canonical = unicodedata.normalize("NFKC", text).casefold()
    risky_spans = [
        match.span()
        for pattern in _CLAIM_PATTERNS
        for match in re.finditer(pattern, canonical, re.IGNORECASE)
    ]
    if not risky_spans:
        return True
    approved_spans: list[tuple[int, int]] = []
    for claim in approved_claim_texts:
        needle = unicodedata.normalize("NFKC", claim).casefold().strip()
        if not needle:
            continue
        start = 0
        while True:
            index = canonical.find(needle, start)
            if index < 0:
                break
            approved_spans.append((index, index + len(needle)))
            start = index + max(1, len(needle))
    return all(
        any(
            approved_start <= start and end <= approved_end
            for approved_start, approved_end in approved_spans
        )
        for start, end in risky_spans
    )


def _id(value: Any) -> str:
    return str(value).lower()


def _anchor_details(anchors: Sequence[Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in anchors:
        data = _data(item)
        identifier = data.get("id")
        anchor_text = data.get("anchor_text", data.get("text"))
        if identifier is not None and anchor_text:
            result[_id(identifier)] = {**data, "anchor_text": str(anchor_text)}
    return result


def _claim_details(claims: Sequence[Any]) -> dict[str, str]:
    result = {}
    for item in claims:
        data = _data(item)
        if data:
            status = str(
                getattr(data.get("status", "APPROVED"), "value", data.get("status", "APPROVED"))
            ).upper()
            if status != "APPROVED":
                continue
            identifier = data.get("id")
            text = data.get("claim_text", data.get("text", ""))
        else:
            identifier = None
            text = str(item)
        if text:
            result[_id(identifier if identifier is not None else text)] = str(text)
    return result


def _post_corpus(post: Any) -> str:
    data = _data(post)
    values: list[str] = []
    for field in ("title", "caption", "ocr_text", "transcript", "visual_summary"):
        if data.get(field):
            values.append(str(data[field]))
    for field in ("hashtags", "mentions"):
        values.extend(str(item).lstrip("#@") for item in data.get(field, ()) or ())
    return normalize_comment(" ".join(values))


def _generic_only(text: str, has_anchor: bool) -> bool:
    stripped = normalize_comment(text).strip()
    compact = stripped.replace(" ", "")
    generic = {normalize_comment(item).replace(" ", "") for item in _GENERIC_ONLY}
    if compact in generic:
        return True
    tokens = [
        item
        for item in re.split(r"[，,。.!！?？\s]+", unicodedata.normalize("NFKC", text).casefold())
        if item
    ]
    return (
        bool(tokens)
        and all(normalize_comment(token).replace(" ", "") in generic for token in tokens)
        and not has_anchor
    )


def _intentional_typo_pattern(text: str) -> bool:
    if any(character in text for character in ("\u200b", "\u200c", "\u200d", "\ufeff")):
        return True
    if re.search(r"(?:[\u4e00-\u9fff][\s._-]){4,}[\u4e00-\u9fff]", text):
        return True
    if re.search(r"\b\w\s*[→>-]+\s*\w\b", text):
        return True
    return False


def compute_quality_score(
    *,
    anchor_coverage: float,
    specificity: float,
    fluency: float,
    voice_match: float,
    novelty: float,
    truthfulness: float,
) -> float:
    score = (
        0.25 * anchor_coverage
        + 0.20 * specificity
        + 0.15 * fluency
        + 0.15 * voice_match
        + 0.15 * novelty
        + 0.10 * truthfulness
    )
    return round(min(1.0, max(0.0, score)), 6)


class QualityEvaluation(BaseModel):
    anchor_coverage: float = Field(ge=0.0, le=1.0)
    specificity: float = Field(ge=0.0, le=1.0)
    fluency: float = Field(ge=0.0, le=1.0)
    voice_match: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    truthfulness: float = Field(ge=0.0, le=1.0)
    identity_consistency: float = Field(ge=0.0, le=1.0)
    duplicate_similarity_max: float = Field(ge=0.0, le=1.0)
    generic_praise_detected: bool
    fake_experience_detected: bool
    fake_identity_detected: bool
    unsupported_claim_detected: bool
    random_typo_pattern_detected: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    decision: QualityDecision
    reasons: list[str] = Field(default_factory=list)
    has_anchor: bool
    anchor_text_supported_by_post: bool
    competitor_attack_detected: bool = False
    external_contact_detected: bool = False
    within_platform_length: bool = True
    voice_profile_compliant: bool = True


class QualityEvaluator:
    def evaluate(
        self,
        candidate: Any,
        *,
        post: Any = None,
        anchors: Sequence[Any] = (),
        recent_comments: Sequence[str] = (),
        approved_claims: Sequence[Any] = (),
        account_identity: Any = None,
        voice_profile: Any = None,
        platform_max_length: int = 500,
        disclosure_prefix: str = "",
    ) -> QualityEvaluation:
        text = _text(candidate).strip()
        candidate_data = _data(candidate)
        anchor_map = _anchor_details(anchors)
        referenced_anchor_ids = [
            _id(item) for item in candidate_data.get("referenced_anchor_ids", ()) or ()
        ]
        referenced = [anchor_map[item] for item in referenced_anchor_ids if item in anchor_map]
        if not referenced:
            referenced = [
                item
                for item in anchor_map.values()
                if normalize_comment(item["anchor_text"]) in normalize_comment(text)
            ]
        matching = [
            item
            for item in referenced
            if normalize_comment(item["anchor_text"]) in normalize_comment(text)
        ]
        has_anchor = bool(matching)
        anchor_coverage = len(matching) / max(1, len(referenced_anchor_ids) or len(referenced))
        corpus = _post_corpus(post)
        if post is None or not _data(post):
            anchor_supported = bool(matching)
        else:
            anchor_supported = bool(matching) and all(
                normalize_comment(item["anchor_text"]) in corpus for item in matching
            )

        generic = _generic_only(text, has_anchor)
        fake_experience = bool(candidate_data.get("uses_first_person_experience")) or _matches_any(
            _FAKE_EXPERIENCE_PATTERNS, text
        )
        identity = _data(account_identity)
        account_kind = str(
            getattr(identity.get("account_kind", ""), "value", identity.get("account_kind", ""))
        ).upper()
        consumer_implication = bool(
            candidate_data.get("implies_consumer_identity")
        ) or _matches_any(_FAKE_IDENTITY_PATTERNS, text)
        fake_identity = consumer_implication and (
            account_kind == AccountKind.BRAND_OFFICIAL.value
            or not bool(identity.get("may_speak_as_consumer", False))
        )

        claim_map = _claim_details(approved_claims)
        referenced_claim_ids = {
            _id(item) for item in candidate_data.get("referenced_claim_ids", ()) or ()
        }
        unknown_claim_ids = referenced_claim_ids - set(claim_map)
        normalized_text = normalize_comment(text)
        referenced_claim_texts = [
            claim_map[identifier] for identifier in referenced_claim_ids if identifier in claim_map
        ]
        referenced_claim_missing_from_text = any(
            normalize_comment(value) not in normalized_text for value in referenced_claim_texts
        )
        risky_claim_language = _matches_any(_CLAIM_PATTERNS, text)
        risky_language_approved = _claim_language_covered_by_approved_text(
            text, referenced_claim_texts
        )
        strategy = str(
            getattr(candidate_data.get("strategy", ""), "value", candidate_data.get("strategy", ""))
        ).upper()
        product_strategy_without_claim = strategy == "PRODUCT_RELATED" and not referenced_claim_ids
        unsupported_claim = (
            bool(unknown_claim_ids)
            or referenced_claim_missing_from_text
            or product_strategy_without_claim
            or (risky_claim_language and not risky_language_approved)
        )

        external_contact = _matches_any(_EXTERNAL_CONTACT_PATTERNS, text)
        competitor_attack = _matches_any(_COMPETITOR_ATTACK_PATTERNS, text)
        typo_pattern = _intentional_typo_pattern(text)
        within_length = 0 < len(text) <= platform_max_length
        voice = _data(voice_profile)
        forbidden = [str(item) for item in voice.get("forbidden_phrases", ()) or ()]
        normalized_forbidden_text = unicodedata.normalize("NFKC", text).casefold()
        voice_compliant = not any(
            unicodedata.normalize("NFKC", item).casefold() in normalized_forbidden_text
            for item in forbidden if item
        )
        if voice.get("active") is False:
            voice_compliant = False

        # A configured identity/disclosure is shared boilerplate, not evidence
        # that the substantive comments repeat. All other checks still inspect
        # the complete text that will be published.
        def without_disclosure(value: str) -> str:
            if disclosure_prefix and value.startswith(disclosure_prefix):
                return value[len(disclosure_prefix):].lstrip()
            return value

        duplicate = max_comment_similarity(
            without_disclosure(text),
            [without_disclosure(value) for value in recent_comments],
        )
        novelty = max(0.0, 1.0 - duplicate)
        alphanumeric = sum(character.isalnum() for character in text)
        specificity = min(1.0, (0.65 if has_anchor else 0.15) + min(alphanumeric, 80) / 240.0)
        if generic:
            specificity = min(specificity, 0.2)
        repeated = bool(re.search(r"(.)\1{5,}", text))
        fluency = 0.35 if not text or repeated else (0.75 if len(text) < 4 else 1.0)
        voice_match = 1.0 if voice_compliant else 0.0
        truthfulness = 0.0 if fake_experience or unsupported_claim or not anchor_supported else 1.0
        identity_consistency = 0.0 if fake_identity else (0.6 if not identity else 1.0)
        score = compute_quality_score(
            anchor_coverage=anchor_coverage,
            specificity=specificity,
            fluency=fluency,
            voice_match=voice_match,
            novelty=novelty,
            truthfulness=truthfulness,
        )

        reasons: list[str] = []
        hard_failures = {
            "FAKE_EXPERIENCE": fake_experience,
            "FAKE_IDENTITY": fake_identity,
            "UNSUPPORTED_CLAIM": unsupported_claim,
            "UNSUPPORTED_ANCHOR": not anchor_supported,
            "COMPETITOR_ATTACK": competitor_attack,
            "EXTERNAL_CONTACT": external_contact,
            "INTENTIONAL_TYPO_PATTERN": typo_pattern,
            "PLATFORM_LENGTH": not within_length,
        }
        reasons.extend(name for name, matched in hard_failures.items() if matched)
        if any(hard_failures.values()) or duplicate >= 0.90:
            if duplicate >= 0.90:
                reasons.append("DUPLICATE")
            decision = QualityDecision.BLOCK
        elif duplicate >= 0.82:
            reasons.append("NEAR_DUPLICATE")
            decision = QualityDecision.REVIEW
        elif not voice_compliant:
            reasons.append("VOICE_PROFILE_VIOLATION")
            decision = QualityDecision.REVIEW
        elif generic:
            reasons.append("GENERIC_PRAISE")
            decision = QualityDecision.REVIEW
        elif score >= 0.80 and duplicate < 0.70:
            decision = QualityDecision.ALLOW
        elif score >= 0.65:
            reasons.append("QUALITY_REVIEW")
            decision = QualityDecision.REVIEW
        else:
            reasons.append("QUALITY_TOO_LOW")
            decision = QualityDecision.REGENERATE
        return QualityEvaluation(
            anchor_coverage=round(anchor_coverage, 6),
            specificity=round(specificity, 6),
            fluency=round(fluency, 6),
            voice_match=round(voice_match, 6),
            novelty=round(novelty, 6),
            truthfulness=round(truthfulness, 6),
            identity_consistency=round(identity_consistency, 6),
            duplicate_similarity_max=round(duplicate, 6),
            generic_praise_detected=generic,
            fake_experience_detected=fake_experience,
            fake_identity_detected=fake_identity,
            unsupported_claim_detected=unsupported_claim,
            random_typo_pattern_detected=typo_pattern,
            quality_score=score,
            decision=decision,
            reasons=list(dict.fromkeys(reasons)),
            has_anchor=has_anchor,
            anchor_text_supported_by_post=anchor_supported,
            competitor_attack_detected=competitor_attack,
            external_contact_detected=external_contact,
            within_platform_length=within_length,
            voice_profile_compliant=voice_compliant,
        )


__all__ = [
    "QualityEvaluation",
    "QualityEvaluator",
    "character_3gram_jaccard",
    "comment_similarity",
    "compute_quality_score",
    "cta_signature",
    "max_comment_similarity",
    "normalize_comment",
    "prefix_signature",
    "word_2gram_jaccard",
]
