from __future__ import annotations

import json
from typing import Any

from web_backend.insight_report_contracts import V5_PROMPT_VERSION
from web_backend.insight_report_evidence import _build_evidence


def analysis() -> dict[str, Any]:
    reason = {
        "value": "FIT_TOO_SMALL",
        "label": "尺码偏小",
        "label_group": "尺码",
        "record_count": 2,
        "percentage": 20.0,
        "subjects": ["PRODUCT"],
    }
    samples = [
        {"comment": "Too small", "product_name": "模拟商品", "product_sku": "TEST-SKU"},
        {"comment": "Too small", "product_name": "模拟商品", "product_sku": "TEST-SKU"},
        {
            "comment": "It doesn�� fit",
            "product_name": "模拟商品",
            "product_sku": "TEST-SKU",
        },
    ]
    semantic_profile = {
        "opinions": [
            {"opinion": "too small", "record_count": 2},
            {"opinion": "It doesn�� fit", "record_count": 1},
        ]
    }
    hotspot = {
        "value": "TEST-SKU",
        "record_count": 2,
        "total_record_count": 5,
        "product_reason_rate": 40.0,
        "overall_reason_rate": 20.0,
        "lift": 2.0,
    }
    return {
        "dashboard_id": "test-dashboard",
        "version_id": "test-version",
        "summary": {
            "record_count": 10,
            "total_record_count": 12,
            "pending_review_record_count": 2,
            "coverage_rate": 83.3,
        },
        "label_group_breakdown": [
            {"value": "尺码", "record_count": 2, "percentage": 20.0}
        ],
        "reasons": [reason],
        "subject_breakdown": [{"value": "PRODUCT", "label": "商品", "record_count": 2}],
        "product_reason_matrix": [{"value": "模拟商品", "total_record_count": 10}],
        "diagnostics": [
            {
                "reason_code": "FIT_TOO_SMALL",
                "selected_reason": reason,
                "trend_summary": {
                    "status": "available",
                    "window_weeks": 4,
                    "early_rate": 10.0,
                    "recent_rate": 20.0,
                    "delta_percentage_points": 10.0,
                },
                "hotspots": [hotspot],
                "variants": [hotspot],
                "samples": samples,
                "semantic_profile": semantic_profile,
            }
        ],
        "issue_cases": [
            {
                "id": "issue_case.FIT_TOO_SMALL.test",
                "reason_code": "FIT_TOO_SMALL",
                "label": "尺码偏小",
                "product_sku": "TEST-SKU",
                "record_count": 2,
                "total_record_count": 5,
                "issue_rate": 40.0,
                "overall_rate": 20.0,
                "lift": 2.0,
                "trend": [{"period_start": "2026-01-05", "record_count": 2}],
                "samples": samples,
                "semantic_profile": semantic_profile,
            }
        ],
        "review_bias": {"status": "not_detected", "note": "模拟审核偏差"},
        "text_quality": {
            "status": "passed",
            "checked_record_count": 10,
            "anomaly_record_count": 2,
        },
        "filter_options": {"listings": ["TEST-LISTING"], "product_names": ["模拟商品"]},
        "sources": [
            {"agent_key": "footwear", "taxonomy_version": "test-taxonomy-2"},
            {"agent_key": "footwear", "taxonomy_version_id": "test-taxonomy-1"},
            {},
        ],
    }


def legacy_evidence(
    context: str = "returns",
    profile: str = "footwear",
    mapping_issue: bool = False,
    text_issue: bool = False,
    provisional: bool = False,
) -> dict[str, Any]:
    raw = analysis()
    if profile == "gloves":
        raw = json.loads(json.dumps(raw).replace("FIT_TOO_SMALL", "GLOVE_SIZE_SMALL"))
    raw["analysis_context"] = context
    raw["sources"] = [{"agent_key": profile}]
    raw["summary"].update(
        total_record_count=12 if provisional else 10,
        pending_review_record_count=2 if provisional else 0,
        coverage_rate=83.3 if provisional else 100.0,
    )
    evidence = _build_evidence(raw, prompt_version=V5_PROMPT_VERSION)
    evidence["source"]["product_mapping"] = {
        "status": "needs_review" if mapping_issue else "passed",
        "listing": "TEST-LISTING",
        "note": "合成商品映射提示",
    }
    evidence["source"]["text_quality"] = {
        "status": "needs_review" if text_issue else "passed",
        "note": "合成文本质量提示",
    }
    return evidence
