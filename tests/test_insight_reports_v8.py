from __future__ import annotations

import sqlite3

import pytest
from test_insight_reports import (
    _complete_report,
    _service_context,
    _set_queued_prompt_version,
)

from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.insight_report_contracts import V7_PROMPT_VERSION, V8_PROMPT_VERSION
from web_backend.insight_report_profiles import resolve_insight_report_profile
from web_backend.insight_reports.v8_evidence import (
    _locations,
    build_theme_evidence,
)
from web_backend.insight_reports.v8_statistics import (
    _sku_size_band,
    _theme_key,
    _Topic,
    collect_report_themes,
)
from web_backend.insight_reports.v8_text_signals import collect_text_signals


def _stats(sources):
    profile = resolve_insight_report_profile(sources)
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.create_function("aligned_group", 3, lambda group, *_: group)
        connection.executescript(
            """
            CREATE TABLE classification_result_records(
                id, result_version_id, classification_key, return_date,
                listing, product_name, product_sku, product_match_status
            );
            CREATE TABLE classification_units(result_version_id, classification_key, comment, classification_json);
            CREATE TABLE classification_unit_labels(
                result_version_id, classification_key, label_code, label_name, label_group, label_kind
            );
            """
        )
        for index in range(15):
            version = "boot" if index < 10 else "glove"
            key = str(index)
            connection.execute(
                "INSERT INTO classification_result_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    version,
                    key,
                    f"2026-{index // 5 + 1:02}-15",
                    "listing",
                    "Demo" if index else "Unknown",
                    "TEST-EU40" if index else "BAD-SKU",
                    "matched" if index else "unmatched",
                ),
            )
            connection.execute(
                "INSERT INTO classification_units VALUES (?, ?, ?, '{}')",
                (version, key, "First wear in a wet pool. Would recommend."),
            )
            labels = [
                ("E", "舒适", "使用感受", "positive"),
                ("FUNCTION_QUICK_DRY_U1", "速干", "功能表现", "positive"),
            ]
            if index in {0, 1, 5, 6, 7, 8, 9, 10}:
                labels.extend(
                    [
                        ("QUALITY_TEAR_U1", "破损", "质量与耐用", "problem"),
                        ("QUALITY_SEAM_FAILURE_U1", "脱线", "质量与耐用", "problem"),
                    ]
                )
            if index in {0, 1, 2}:
                labels.append(
                    ("FIT_TOO_TIGHT_NARROW_U1", "窄", "尺码与适配", "problem")
                )
            if index in {1, 2, 3}:
                labels.append(("FIT_TOO_LOOSE_WIDE_U1", "宽", "尺码与适配", "problem"))
            if index in {1, 2, 3, 4}:
                labels.append(("FUNCTION_GRIP_U1", "抓地", "功能表现", "problem"))
            connection.executemany(
                "INSERT INTO classification_unit_labels VALUES (?, ?, ?, ?, ?, ?)",
                [(version, key, *label) for label in labels],
            )
        scope = InsightQueryScope(
            connection, {}, "1=1", [], "1=1", [], False, "", "", "", True
        )
        return collect_report_themes(scope, [], profile)


def _evidence(sources):
    return build_theme_evidence(
        {
            "sources": sources,
            "summary": {
                "record_count": 15,
                "total_record_count": 15,
                "pending_review_record_count": 1,
                "product_unmatched_count": 1,
            },
            "filter_options": {},
            "text_quality": {},
            "review_bias": {},
            "report_themes": _stats(sources),
        }
    )


def test_footwear_theme_evidence_uses_feedback_denominators() -> None:
    evidence = _evidence([{"agent_key": "footwear"}])
    themes = {item["name"]: item for item in evidence["blueprint"]["themes"]}
    assert list(themes) == ["产品核心价值", "质量与耐用", "尺码与适配", "防滑与抓地"]
    core = themes["产品核心价值"]
    assert core["facts"][0].startswith("15 / 15")
    assert "舒适 15 条" in str(core["facts"]) and "速干 15 条" in str(core["facts"])
    assert "8 条肯定产品价值的反馈同时报告了质量问题" in str(core["facts"])
    durable = themes["质量与耐用"]
    assert durable["facts"][0].startswith("8 / 15")
    assert "破损 8 条" in str(durable["facts"]) and "脱线 8 条" in str(durable["facts"])
    assert "可比月份样本量有限" in str(durable["facts"])
    assert "首用或短期失效相关表达命中 8 条" in str(durable["facts"])
    assert "偏小 3 条、偏大 3 条，重叠 2 条，共涉及 4 条" in str(themes["尺码与适配"])
    grip = themes["防滑与抓地"]
    assert "湿滑地面场景" not in str(grip["facts"])
    assert any(
        evidence["catalog"][ref]["label"] == "湿滑地面场景"
        for ref in grip["evidence_ids"]
    )
    assert "明确推荐" in str(themes["产品核心价值"])
    assert "BAD-SKU" not in str(evidence)
    assert "TEST-EU40" in str(evidence)
    assert "EU40–<44" in str(evidence)
    assert "14 / 15" in str(evidence["blueprint"]["boundaries"])


@pytest.mark.parametrize(
    "sources",
    [[{"agent_key": "gloves"}], [{"agent_key": "footwear"}, {"agent_key": "gloves"}]],
)
def test_generic_and_gloves_use_taxonomy_groups(sources) -> None:
    evidence = _evidence(sources)
    names = {theme["name"] for theme in evidence["blueprint"]["themes"]}
    assert {"产品核心价值", "功能表现"} <= names and "防滑与抓地" not in names
    assert evidence["blueprint"]["themes"][0]["name"] == "产品核心价值"
    assert "鞋款" not in str(evidence["blueprint"])


def test_current_v8_runs_and_v7_versions_remain_retryable(tmp_path) -> None:
    _, dashboard, service, _ = _service_context(tmp_path, client_payload={})
    report = _complete_report(dashboard, service, prompt_version=V8_PROMPT_VERSION)
    assert report["status"] == "completed", report
    assert report["prompt_version"] == V8_PROMPT_VERSION
    assert report["content"]["report_type"] == "theme_insight"
    assert report["content"]["themes"]
    older = _complete_report(dashboard, service, prompt_version=V7_PROMPT_VERSION)
    assert older["content"]["report_type"] == "semantic_insight"
    queued = service.create_for_dashboard(
        dashboard["id"],
        dashboard["version"]["version_id"],
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    _set_queued_prompt_version(service, queued["id"], V7_PROMPT_VERSION)
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE ai_insight_reports SET status = 'failed' WHERE id = ?",
            (queued["id"],),
        )
    retry = service.retry(queued["id"], "user-1")
    assert retry["prompt_version"] == V7_PROMPT_VERSION
    assert retry["parent_job_id"] == queued["id"]


@pytest.mark.parametrize(
    "text",
    [
        "It broke after one wear.",
        "Wore it once.",
        "Tore after a couple of hours.",
        "Fell apart in 3 hrs.",
        "Lasted one day.",
        "Broke within the first few days.",
        "Wore out within a week.",
    ],
)
def test_short_use_phrasing(text):
    assert "首用或短期失效" in collect_text_signals(text)


def test_explicit_sku_range_is_kept():
    assert _sku_size_band("TEST-38-39") == "38–39"
    assert _sku_size_band("TEST-EU38-EU39") == "EU38–39"
    assert _sku_size_band("TEST-EU40") == "EU40–<44"


def test_low_denominator_is_not_a_location():
    tiny = ("SKU", "SMALL", "Demo", "listing")
    sufficient = ("SKU", "FULL", "Demo", "listing")
    topic = _Topic()
    topic.locations.update({tiny: 4, sufficient: 4})
    _, _, stats = _locations(topic, {tiny: 5, sufficient: 10})["sku"]
    assert stats["location"] == sufficient
    assert stats["total"] == 10


def test_information_group_displays_natural_title():
    profile = resolve_insight_report_profile([])
    assert _theme_key("CUSTOM", "整体反馈与信息不足", profile) == "使用场景与购买意愿"
