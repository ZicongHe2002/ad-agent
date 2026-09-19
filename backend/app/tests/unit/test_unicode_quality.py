import pytest

from app.agents.quality_evaluator import QualityEvaluator
from app.domain.enums import QualityDecision


@pytest.mark.parametrize("suffix,reason", [
    ("100%有效。", "UNSUPPORTED_CLAIM"),
    ("１００％有效。", "UNSUPPORTED_CLAIM"),
    ("https://example.com", "EXTERNAL_CONTACT"),
    ("ｈｔｔｐｓ：／／example.com", "EXTERNAL_CONTACT"),
])
def test_equivalent_unicode_cannot_bypass_claim_or_contact_checks(suffix, reason):
    result = QualityEvaluator().evaluate(
        {"comment": f"红色外套这个细节很好，{suffix}", "referenced_anchor_ids": ["anchor"]},
        post={"caption": "红色外套"},
        anchors=[{"id": "anchor", "anchor_text": "红色外套"}],
        account_identity={"account_kind": "BRAND_OFFICIAL"},
        approved_claims=[],
    )
    assert result.decision == QualityDecision.BLOCK
    assert reason in result.reasons
