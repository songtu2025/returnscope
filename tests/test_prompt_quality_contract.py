import json

import pytest

from return_semantics import prompt
from return_semantics.schemas import ModelClassification, SentimentCode


@pytest.mark.parametrize("profile", ["legacy_v3", "keyword_free_v1", "semantic_v1"])
def test_profiles_preserve_evidence_and_event_boundaries(taxonomy, claims, profile):
    candidate = taxonomy.model_copy(deep=True)
    candidate.recognition_profile = profile
    comment = "标题：附件很好。正文：主体在干燥环境中使用舒适。"
    category = {"name": "测试品类"}

    messages = prompt.build_messages(comment, candidate, claims, category)
    system = messages[0]["content"]

    assert json.loads(messages[1]["content"]) == {
        "category": category,
        "comment": comment,
    }
    assert comment not in system
    for boundary in (
        "完整句子或分句",
        "动作宾语、否定、程度、条件和时间",
        "不从其他未引用句子补入",
        "条件化购买建议可以是 AFFIRMED",
        "尚未发生的预测、假设、担忧",
        "不能把使用方法建议变成购买推荐",
        "不同购买对象、部位、时间阶段、使用场景或独立事件不得机械合并",
        "同一事件的重复措辞不是新事实",
        "同一事件优先最具体",
        "不再重复生成未知语义",
        "不按更大或更小的词面反推缺陷",
    ):
        assert boundary in system


@pytest.mark.parametrize("sentiment", list(SentimentCode))
def test_json_example_uses_allowed_direction(taxonomy, claims, sentiment):
    candidate = taxonomy.model_copy(deep=True)
    candidate.labels[0].allowed_sentiments = [sentiment]
    system = prompt.build_messages("测试评论", candidate, claims)[0]["content"]
    example_text = system.split("JSON 输出示例：\n", 1)[1]
    example, _ = json.JSONDecoder().raw_decode(example_text)
    result = ModelClassification.model_validate(example)

    assert result.semantic_units[0].sentiment == sentiment
    assert result.semantic_units[0].label_code == candidate.labels[0].code
    assert result.primary_label_codes == (
        [candidate.labels[0].code] if sentiment == SentimentCode.NEGATIVE else []
    )


def test_user_feedback_prompt_has_no_return_or_negative_assumption(
    taxonomy,
    claims,
) -> None:
    system = prompt.build_messages(
        "Great fit",
        taxonomy,
        claims,
        analysis_context="user_feedback",
    )[0]["content"]

    assert "通用用户反馈分析" in system
    assert "正向、负向、中性和混合表达都是有效语义" in system
    assert "不得预设用户正在退货、投诉或描述问题" in system
    assert "只有正向体验时，退货原因仍然未知" not in system


@pytest.mark.parametrize(
    ("profile", "old_version"),
    [
        ("legacy_v3", "category-semantic-v4"),
        ("keyword_free_v1", "category-keyword-free-v2"),
        ("semantic_v1", "category-semantic-evidence-v2"),
    ],
)
def test_previous_prompt_validation_is_invalidated(
    taxonomy, monkeypatch, profile, old_version
):
    candidate = taxonomy.model_copy(deep=True)
    candidate.recognition_profile = profile
    snapshot = {"taxonomy": candidate.model_dump(mode="json")}
    with monkeypatch.context() as context:
        context.setattr(prompt, "prompt_version", lambda _: old_version)
        previous = prompt.recognition_fingerprint(candidate)

    source = {"recognition_contract": {"candidate": {"fingerprint": previous}}}
    assert not prompt.validation_contract_matches(snapshot, source)
    source["recognition_contract"]["candidate"]["fingerprint"] = (
        prompt.recognition_fingerprint(candidate)
    )
    assert prompt.validation_contract_matches(snapshot, source)
