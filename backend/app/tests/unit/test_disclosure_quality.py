import pytest

from app.agents.quality_evaluator import QualityEvaluator
from app.domain.enums import QualityDecision

PREFIX = "【云绒官方账号｜AI辅助生成】"
BODY = "红色外套与画面中的落叶相呼应，暖色搭配显得很协调。"


def evaluate(recent):
    return QualityEvaluator().evaluate(
        {"comment": PREFIX + BODY, "referenced_anchor_ids": ["anchor"]},
        post={"caption": "红色外套与落叶"},
        anchors=[{"id": "anchor", "anchor_text": "红色外套"}],
        account_identity={"account_kind": "BRAND_OFFICIAL"},
        recent_comments=recent,
        disclosure_prefix=PREFIX,
    )


def test_shared_disclosure_does_not_make_distinct_comments_near_duplicates():
    result = evaluate([PREFIX + "夜晚的城市天际线被蓝色灯光勾勒出来，长曝光记录了车辆轨迹。"])
    assert result.decision == QualityDecision.ALLOW
    assert result.duplicate_similarity_max < 0.7


@pytest.mark.parametrize("previous", [BODY, PREFIX + BODY])
def test_disclosure_does_not_hide_duplicate_content(previous):
    result = evaluate([previous])
    assert result.decision == QualityDecision.BLOCK
    assert result.duplicate_similarity_max == 1.0
    assert "DUPLICATE" in result.reasons
