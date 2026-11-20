import pytest
from test_insight_reports import (
    _complete_report,
    _service_context,
    _set_queued_prompt_version,
)
from test_insight_reports_v8 import _evidence, _stats

from web_backend.insight_report_contracts import V8_PROMPT_VERSION, V9_PROMPT_VERSION
from web_backend.insight_reports.v9_content import assemble_concise_content
from web_backend.insight_reports.v9_evidence import prepare_concise_evidence


def test_concise_report_preserves_counts_and_anchored_prose():
    sources = [{"agent_key": "footwear"}]
    stats = _stats(sources)
    stats["topics"]["尺码与适配"].labels[("FIT_TOO_SMALL_U1", "偏小")] = 2
    evidence = prepare_concise_evidence(_evidence(sources), stats)
    brief = evidence["blueprint"]["concise"]
    core, quality, sizing, _, coverage = brief["insights"]
    accepted = "将原款舒适表现作为改款样品的体验对照。"
    content = assemble_concise_content(
        evidence,
        {
            "insights": [
                {
                    "id": core["id"],
                    "meaning": accepted,
                    "evidence_ids": core["evidence_ids"][:1],
                },
                {
                    "id": quality["id"],
                    "meaning": "绝大多数问题由异常工厂引起，共 99 条。",
                    "evidence_ids": quality["evidence_ids"][:1],
                },
                {
                    "id": sizing["id"],
                    "meaning": "按同款试穿复现前脚掌与鞋跟的受力位置。",
                    "evidence_ids": ["scope"],
                },
            ]
        },
    )
    assert "舒适和合脚" in content.title
    assert len(content.insights) == 5
    assert (
        "舒适 15 条（100.0%）" in content.insights[0].fact
        and content.insights[0].meaning == accepted
    )
    assert "8 条负向反馈，其中 8 条（100.0%）" in content.insights[1].fact
    assert content.insights[1].meaning == quality["meaning"]
    assert "「偏小」标签 2 条" in content.insights[2].fact
    assert (
        "偏小方向 3 条、偏大方向 3 条，重叠 2 条，共涉及 4 条"
        in content.insights[2].fact
    )
    assert content.insights[2].meaning == sizing["meaning"]
    assert "缺少可靠商品映射" in coverage["fact"]
    assert (
        "主要 Listing 的样本集中度"
        == evidence["catalog"]["scope.leading-listing"]["label"]
    )
    assert [action.priority for action in content.actions] == ["P0", "P1", "P1", "P1"]
    assert all(
        ref in evidence["catalog"]
        for action in content.actions
        for ref in action.evidence_ids
    )
    assert any("销量或订单总量" in note for note in content.boundaries)


@pytest.mark.parametrize("historical_version", [V8_PROMPT_VERSION, V9_PROMPT_VERSION])
def test_v9_remains_readable_and_themed_reports_keep_retry_version(
    tmp_path, historical_version
):
    _, dashboard, service, _ = _service_context(tmp_path, client_payload={})
    report = _complete_report(dashboard, service, prompt_version=V9_PROMPT_VERSION)
    assert report["status"] == "completed", report
    assert report["prompt_version"] == V9_PROMPT_VERSION
    assert report["content"]["report_type"] == "concise_insight"
    queued = service.create_for_dashboard(
        dashboard["id"],
        dashboard["version"]["version_id"],
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    _set_queued_prompt_version(service, queued["id"], historical_version)
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE ai_insight_reports SET status = 'failed' WHERE id = ?",
            (queued["id"],),
        )
    retry = service.retry(queued["id"], "user-1")
    assert retry["prompt_version"] == historical_version
    assert retry["parent_job_id"] == queued["id"]
