from __future__ import annotations

from test_insight_reports_v8 import _evidence

from web_backend.insight_reports.v8_content import assemble_theme_content
from web_backend.insight_reports.v8_evidence import _trend
from web_backend.insight_reports.v8_statistics import _Topic


def test_v8_narrative_references_only_current_theme_and_keeps_partial_mapping() -> None:
    evidence = _evidence([{"agent_key": "footwear"}])
    theme = evidence["blueprint"]["themes"][0]
    prefix = theme["id"]
    result = assemble_theme_content(
        evidence,
        {
            "themes": [
                {
                    "id": prefix,
                    "title": "替换标题",
                    "diagnosis": (
                        f"将商品组 [[{prefix}.sku]] 与总体 [[{prefix}.volume]] 对照，"
                        "判断价值反馈是否集中在特定样本。"
                    ),
                    "hypothesis": (
                        f"若按使用场景分组后 [[{prefix}.volume]] 的优势消失，"
                        "场景稳定性假设不成立。"
                    ),
                    "impact": "[[theme.2.volume]]",
                    "action": f"抽取 [[{prefix}.sku]] 的同范围反馈作为对象，对照同品类未命中样本。",
                    "metric": f"以 [[{prefix}.volume]] 为基准，分子为正向反馈数，分母为同范围反馈数。",
                }
            ]
        },
    ).themes[0]
    assert result.title == theme["title"]
    assert "TEST-EU40" in result.diagnosis
    assert "场景稳定性假设不成立" in result.hypothesis
    assert "15 / 15" in result.metric
    assert "分子为正向反馈数" in result.metric
    assert "theme.2" not in result.impact
    assert "TEST-EU40" in result.action
    assert "同品类未命中样本" in result.action


def test_management_summary_proposes_evidence_backed_priorities():
    evidence = _evidence([{"agent_key": "footwear"}])
    blueprint = evidence["blueprint"]
    core, durability, sizing = blueprint["executive_summary"]
    assert "15 条反馈肯定" in core["statement"] and "8 条肯定" in core["statement"]
    assert (
        "8 条负向" in durability["statement"]
        and "8 条提及首用或短期失效" in durability["statement"]
    )
    assert "破损" in durability["statement"] and "脱线" in durability["statement"]
    assert "偏小 3 条、偏大 3 条，重叠 2 条，共涉及 4 条" in sizing["statement"]
    for summary, theme in zip(
        blueprint["executive_summary"], blueprint["themes"], strict=False
    ):
        assert summary["statement"] != theme["facts"][0]
        assert set(summary["evidence_ids"]) <= set(theme["evidence_ids"])
    assert "8条提及首用或短期失效" in blueprint["themes"][1]["title"]
    assert "涉及4条反馈" in blueprint["themes"][2]["title"]
    assert all(len(theme["facts"]) <= 6 for theme in blueprint["themes"])


def test_month_trend_uses_themes_direction_and_monthly_feedback_denominator():
    months = {"2026-04": 10, "2026-05": 10, "2026-06": 10}
    topic = _Topic(positive=8, negative=5)
    topic.negative_months.update({"2026-04": 1, "2026-05": 3, "2026-06": 1})
    topic.positive_months.update({"2026-04": 5, "2026-05": 1, "2026-06": 2})
    label, peak, full = _trend(topic, months)["trend"]
    assert label == "各月负向样本占比"
    assert "2026-05" in peak and "30.0%" in peak
    assert [item["count"] for item in full] == [1, 3, 1]
    topic.negative = 0
    _, peak, full = _trend(topic, months)["trend"]
    assert "正向" in peak and [item["count"] for item in full] == [5, 1, 2]


def test_narrative_rejects_generic_or_unsubstantiated_language():
    evidence = _evidence([{"agent_key": "footwear"}])
    prefix = evidence["blueprint"]["themes"][0]["id"]
    result = assemble_theme_content(
        evidence,
        {
            "themes": [
                {
                    "id": prefix,
                    "diagnosis": f"值得核对 [[{prefix}.volume]] [[{prefix}.polarity]]",
                    "hypothesis": f"可能有差异 [[{prefix}.volume]]",
                    "impact": "问题已被证实由生产工艺造成。",
                    "action": f"持续关注 [[{prefix}.volume]]，当前退货率 99%",
                    "metric": f"对照 [[{prefix}.volume]]，跟踪占比。",
                }
            ]
        },
    ).themes[0]
    assert "值得核对" not in result.diagnosis
    assert "可能有差异" not in result.hypothesis
    assert "生产工艺" not in result.impact
    assert "持续关注" not in result.action and "99" not in result.action
    assert "分子" in result.metric and "分母" in result.metric


def test_month_trend_compares_consecutive_phases_preceding_peak():
    months = {f"2026-{month:02}": 10 for month in range(4, 10)}
    topic = _Topic(negative=20)
    topic.negative_months.update(dict(zip(months, [1, 1, 4, 5, 7, 2], strict=True)))
    _, value, full = _trend(topic, months)["trend"]
    assert "2026-04 至 2026-05 为 10.0%（2/20）" in value
    assert "2026-06 至 2026-08 为 53.3%（16/30）" in value
    assert len(full) == 6
