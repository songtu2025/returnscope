from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from test_insight_reports import _complete_report, _service_context

from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.insight_report_contracts import V7_PROMPT_VERSION
from web_backend.insight_report_profiles import get_insight_report_profile
from web_backend.insight_reports.v7_content import assemble_semantic_content
from web_backend.insight_reports.v7_evidence import build_semantic_evidence
from web_backend.insight_reports.v7_quality import evaluate_semantic_quality
from web_backend.insight_reports.v7_statistics import collect_report_signals


def test_v7_current_generation_uses_dashboard_scope_and_fixed_metrics(tmp_path) -> None:
    payload = {
        "issues": [
            {
                "id": "signal.risk.FIT_TOO_SMALL_U1",
                "rank": 99,
                "metrics": {"return_sample_share": 5},
                "scope": {"sku": "model-value"},
                "evidence_ids": ["model.ref"],
                "evidence_explanation": "总体发生率百分之九十",
                "unknown": None,
            }
        ]
    }
    _, dashboard, service, captured = _service_context(tmp_path, client_payload=payload)
    report = _complete_report(dashboard, service, prompt_version=V7_PROMPT_VERSION)
    overview = report["content"]["overview"]
    stats = service.dashboard_service.insights(
        dashboard["id"], dashboard["version"]["version_id"]
    )
    assert report["prompt_version"] == V7_PROMPT_VERSION
    assert report["version_no"] == 1
    assert overview["total"] == stats["total_record_count"] == 2
    assert overview["negative"] == 2
    issue = report["content"]["issues"][0]
    assert issue["id"] == payload["issues"][0]["id"]
    assert issue["rank"] == 1
    assert issue["metrics"]["return_sample_share"] == 100
    assert not issue["scope"]["sku"]
    assert "model.ref" not in issue["evidence_ids"]
    assert "发生率" not in issue["evidence_explanation"]
    assert issue["readiness"]["status"] == "diagnostic_only"
    assert len(report["content"]["executive_summary"]) == 3
    assert "具体商品" in captured["messages"][0]["content"]


def test_v7_scans_all_labels_before_selecting_each_kind() -> None:
    labels = [
        {
            "code": f"NEG_{index:02}",
            "label": f"问题 {index}",
            "positive": 0,
            "negative": 30 - index,
            "matched": 30 - index,
        }
        for index in range(20)
    ]
    labels.append(
        {"code": "ZZ", "label": "细节表现", "positive": 4, "negative": 1, "matched": 5}
    )
    overview = {
        "total": 60,
        "labeled": 55,
        "positive": 4,
        "negative": 50,
        "mixed": 1,
        "unclear": 5,
    }
    analysis = {
        "dashboard_id": "dash",
        "version_id": "v1",
        "summary": {"record_count": 60},
        "sources": [{"agent_key": "generic"}],
        "filter_options": {},
        "reasons": [],
        "text_quality": {"status": "passed"},
        "review_bias": {},
        "report_signals": {"overview": overview, "labels": labels},
    }
    dashboard_service = SimpleNamespace(report_diagnostics=lambda *_: [])
    evidence = build_semantic_evidence(dashboard_service, analysis)
    report = assemble_semantic_content(evidence, {}).model_dump()
    assert [item["kind"] for item in report["issues"][:4]] == [
        "risk",
        "polarization",
        "opportunity",
        "data_gap",
    ]
    assert report["issues"][1]["id"] == "signal.polarization.ZZ"
    assert report["issues"][2]["id"] == "signal.opportunity.ZZ"
    assert report["issues"][1]["metrics"]["matched_return_samples"] == 5
    assert all(
        ref in evidence["catalog"]
        for item in report["issues"]
        for ref in item["evidence_ids"]
    )
    assert "鞋" not in str(report)
    analysis["report_signals"]["labels"].reverse()
    assert build_semantic_evidence(dashboard_service, analysis) == evidence

    analysis["report_signals"]["labels"] = []
    unlabeled = build_semantic_evidence(dashboard_service, analysis)["blueprint"][
        "issues"
    ]
    assert [item["kind"] for item in unlabeled[:4]] == [
        "risk",
        "polarization",
        "opportunity",
        "data_gap",
    ]


def test_v7_quality_masks_product_conclusions_and_live_text(tmp_path) -> None:
    _, dashboard, service, _ = _service_context(tmp_path)
    report = _complete_report(dashboard, service, prompt_version=V7_PROMPT_VERSION)
    analysis = service._report_analysis(report)
    analysis["summary"]["product_unmatched_count"] = 1
    safe = build_semantic_evidence(service.dashboard_service, analysis)
    assert safe["source"]["product_mapping"]["status"] == "needs_review"
    assert not any(".hotspot." in key or ".variant." in key for key in safe["catalog"])
    content = assemble_semantic_content(safe, {}).model_dump()
    assert all(not issue["scope"].get("sku") for issue in content["issues"])
    flagged = evaluate_semantic_quality(
        content, safe, {"status": "needs_review", "anomaly_record_count": 1}
    )
    assert {issue["code"] for issue in flagged["quality_gate"]["issues"]} == {
        "product_mapping",
        "text_quality",
    }
    assert all(
        item["readiness"]["status"] == "diagnostic_only"
        for item in flagged["content"]["issues"]
    )


@pytest.mark.parametrize(
    "agent_key, category", [("footwear", "鞋履"), ("gloves", "手套")]
)
def test_v7_category_profile_is_metadata(agent_key, category, tmp_path) -> None:
    _, dashboard, service, _ = _service_context(tmp_path)
    report = _complete_report(dashboard, service, prompt_version=V7_PROMPT_VERSION)
    analysis = service._report_analysis(report)
    analysis["sources"] = [{"agent_key": agent_key}]
    evidence = build_semantic_evidence(service.dashboard_service, analysis)
    assert evidence["source"]["report_profile"]["category_name"] == category
    assert evidence["blueprint"]["issues"][0]["scope"]["category"] == category


def test_v7_polarity_deduplicates_legacy_labels_and_semantic_units() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE records(result_version_id, classification_key);
            CREATE TABLE classification_unit_labels(
                result_version_id, classification_key, label_code, label_name, label_kind
            );
            CREATE TABLE classification_units(result_version_id, classification_key, classification_json);
            INSERT INTO records VALUES ('v', 'mixed'), ('v', 'mixed'), ('v', 'positive'),
                                       ('v', 'negative'), ('v', 'neutral'), ('v', 'empty');
            INSERT INTO classification_unit_labels VALUES
                ('v', 'mixed', 'A', '甲', 'problem'),
                ('v', 'mixed', 'A', '甲', 'positive'),
                ('v', 'negative', 'A', '甲', 'problem'),
                ('v', 'positive', 'B', '乙', 'positive');
            INSERT INTO classification_units VALUES
                ('v', 'mixed', '{"semantic_units": [
                    {"sentiment": "POSITIVE", "label_code": "A"},
                    {"sentiment": "POSITIVE", "label_code": "A"},
                    {"sentiment": "NEGATIVE", "label_code": "A"}
                ]}'),
                ('v', 'neutral', '{"semantic_units": [
                    {"sentiment": "NEUTRAL", "label_code": "A"}
                ]}');
            """
        )
        scope = InsightQueryScope(
            connection, {}, "1=1", [], "1=1", [], False, "", "", "", True, "records"
        )
        result = collect_report_signals(scope)
    assert result["overview"] == {
        "mixed": 2,
        "positive": 1,
        "negative": 1,
        "unclear": 2,
        "labeled": 5,
        "total": 6,
    }
    assert result["labels"][0] == {
        "code": "A",
        "label": "甲",
        "positive": 2,
        "negative": 3,
        "matched": 3,
    }


@pytest.mark.parametrize(
    "category,left_code,right_code,shared_weight",
    [
        ("footwear", "FIT_TOO_SMALL", "FIT_TOO_LARGE", 0),
        ("gloves", "GLOVE_SIZE_SMALL", "GLOVE_SIZE_LARGE", 2),
    ],
)
def test_v7_opposing_labels_use_weighted_union(
    category: str, left_code: str, right_code: str, shared_weight: int
) -> None:
    profile = get_insight_report_profile(category)
    [[left, right]] = profile.snapshot()["polarization_pairs"]
    assert left[:2] == [left_code, f"{left_code}_U1"]
    assert right[:2] == [right_code, f"{right_code}_U1"]
    if category == "footwear":
        assert "FIT_TOO_TIGHT_NARROW_U1" in left and "FIT_TOO_SHORT_U1" in left
        assert "FIT_TOO_LOOSE_WIDE_U1" in right and "FIT_TOO_LONG_U1" in right
    else:
        assert len(left) == len(right) == 2
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE records(result_version_id, classification_key);
            CREATE TABLE classification_unit_labels(
                result_version_id, classification_key, label_code, label_name, label_kind
            );
            CREATE TABLE classification_units(
                result_version_id, classification_key, classification_json
            );
            INSERT INTO records VALUES ('old', 'small'), ('current', 'large');
            """
        )
        connection.executemany(
            "INSERT INTO records VALUES ('current', 'both')",
            [()] * shared_weight,
        )
        connection.executemany(
            "INSERT INTO classification_unit_labels VALUES (?, ?, ?, ?, 'problem')",
            [
                ("old", "small", left_code, "偏小"),
                ("current", "large", f"{right_code}_U1", "偏大"),
                ("current", "both", left_code, "偏小"),
                ("current", "both", f"{left_code}_U1", "偏小"),
                ("current", "both", f"{right_code}_U1", "偏大"),
            ],
        )
        scope = InsightQueryScope(
            connection, {}, "1=1", [], "1=1", [], False, "", "", "", True, "records"
        )
        signals = collect_report_signals(scope, profile.polarization_pairs)
        assert collect_report_signals(scope)["paired_labels"] == []
    pair = signals["paired_labels"][0]
    assert pair["left_count"] == pair["right_count"] == 1 + shared_weight
    assert pair["overlap"] == shared_weight
    assert pair["union_count"] == 2 + shared_weight
    analysis = {
        "dashboard_id": "dash",
        "version_id": "v1",
        "summary": {"record_count": 2 + shared_weight},
        "sources": [{"agent_key": category}],
        "filter_options": {},
        "reasons": [],
        "text_quality": {"status": "passed"},
        "review_bias": {},
        "report_signals": signals,
    }
    dashboard_service = SimpleNamespace(report_diagnostics=lambda *_: [])
    evidence = build_semantic_evidence(dashboard_service, analysis)
    issue = next(
        item
        for item in evidence["blueprint"]["issues"]
        if item["kind"] == "polarization"
    )
    assert issue["id"] == f"signal.polarization.pair.{left_code}.{right_code}"
    assert issue["title"] == "偏小与偏大的反馈分化"
    assert (
        f"偏小 {1 + shared_weight} 条，偏大 {1 + shared_weight} 条。" in issue["known"]
    )
    assert issue["metrics"]["matched_return_samples"] == pair["union_count"]
    assert issue["metrics"]["return_sample_share"] == 100
    assert evidence["catalog"][issue["id"]]["data"]["overlap"] == shared_weight
    signals["labels"].reverse()
    assert build_semantic_evidence(dashboard_service, analysis) == evidence
    analysis["sources"] = [{"agent_key": "generic"}]
    generic = build_semantic_evidence(dashboard_service, analysis)
    assert generic["source"]["report_profile"]["polarization_pairs"] == []
    assert not any(
        item["kind"] == "polarization" for item in generic["blueprint"]["issues"]
    )
    assert "鞋" not in str(generic["blueprint"])
