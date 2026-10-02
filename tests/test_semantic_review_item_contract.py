import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from return_semantics.semantic_review import build_semantic_review_view


@pytest.mark.parametrize("object_input", [False, True], ids=["mapping", "object"])
@pytest.mark.parametrize(
    ("result", "expected", "count_key"),
    [
        pytest.param(
            {
                "extracted_facts": [
                    {
                        "fact_id": "F1",
                        "opinion": "尺码偏小",
                        "evidence_spans": [
                            {"text": "Too small", "source": "TITLE"},
                            {"text": "Too small", "source": "BODY"},
                            {"text": "Tight", "source": "BODY"},
                        ],
                    }
                ],
                "fact_mappings": [
                    {
                        "fact_id": "F1",
                        "label_codes": ["FIT_TOO_SMALL"],
                        "reason": "合成映射原因",
                    }
                ],
            },
            {
                "item_id": "fact:F1",
                "fact_id": "F1",
                "evidence_text": "Too small | Tight",
                "evidence_source": "TITLE_AND_BODY",
                "opinion": "尺码偏小",
                "label_code": "FIT_TOO_SMALL",
                "label_path": ["尺码与合脚", "偏小"],
                "disposition": "MAPPED",
                "reason": "合成映射原因",
            },
            "mapped",
            id="fact",
        ),
        pytest.param(
            {
                "semantic_units": [
                    {
                        "opinion": "尺码偏小",
                        "label_code": "FIT_TOO_SMALL",
                        "evidence": "Too small",
                        "evidence_source": "BODY",
                        "decision_reason": "合成原因",
                    }
                ]
            },
            {
                "item_id": "semantic:a760b1c4e79cb903",
                "fact_id": "",
                "evidence_text": "Too small",
                "evidence_source": "BODY",
                "opinion": "尺码偏小",
                "label_code": "FIT_TOO_SMALL",
                "label_path": ["尺码与合脚", "偏小"],
                "disposition": "MAPPED",
                "reason": "合成原因",
            },
            "mapped",
            id="legacy-unit",
        ),
        pytest.param(
            {
                "unknown_semantics": [
                    {
                        "opinion": "没有标签",
                        "evidence": "Unusual",
                        "disposition": "TAXONOMY_GAP",
                        "reason": "合成缺口",
                    }
                ]
            },
            {
                "item_id": "unknown:766efd51cdaddc16",
                "fact_id": "",
                "evidence_text": "Unusual",
                "evidence_source": "COMMENT",
                "opinion": "没有标签",
                "label_code": "",
                "label_path": [],
                "disposition": "TAXONOMY_GAP",
                "reason": "合成缺口",
            },
            "taxonomy_gap",
            id="unknown",
        ),
        pytest.param(
            {
                "review_diagnostics": [
                    {"code": "SECONDARY_MODEL_TIMEOUT", "detail": "合成超时记录"}
                ]
            },
            {
                "item_id": (
                    "analysis-failure:SECONDARY_MODEL_TIMEOUT:438bb6c7:8ca994253ec39cee"
                ),
                "fact_id": "",
                "evidence_text": "",
                "evidence_source": "SYSTEM",
                "opinion": "风险复核调用超时",
                "label_code": "",
                "label_path": [],
                "disposition": "ANALYSIS_FAILURE",
                "reason": "合成超时记录",
                "diagnostic_domain": "TECHNICAL_RUNTIME",
                "diagnostic_code": "SECONDARY_MODEL_TIMEOUT",
                "diagnostic_title": "风险复核调用超时",
                "detail_status": "NOT_APPLICABLE",
                "primary_result": "",
                "secondary_result": "",
                "detail": "合成超时记录",
                "action": "无需业务员核验；请系统重试风险复核。",
                "business_review_required": False,
            },
            "analysis_failure",
            id="analysis-failure",
        ),
    ],
)
def test_entrypoints_keep_full_output_and_input_unchanged(
    result, expected, count_key, object_input, taxonomy
) -> None:
    source = (
        json.loads(
            json.dumps(result), object_hook=lambda fields: SimpleNamespace(**fields)
        )
        if object_input
        else deepcopy(result)
    )
    before = deepcopy(source)
    summary = {
        "total": 1,
        "mapped": 0,
        "no_tag_needed": 0,
        "taxonomy_gap": 0,
        "true_ambiguity": 0,
        "analysis_failure": 0,
        "unexplained_fragment_count": 0,
        "complete": count_key == "mapped",
    }
    summary[count_key] = 1
    expected_view = {
        "semantic_items": [expected],
        "coverage_summary": summary,
        "unexplained_fragments": [],
    }

    assert build_semantic_review_view(source, "", taxonomy) == expected_view
    assert build_semantic_review_view(source, "", taxonomy) == expected_view
    assert source == before


@pytest.mark.parametrize(
    ("spans", "text", "source"),
    [
        ([], "", "COMMENT"),
        ([{"text": " ", "source": "TITLE"}], "", "COMMENT"),
        ([{"text": " Small "}], "Small", "COMMENT"),
        ([{"text": "Small", "source": None}], "Small", "COMMENT"),
        (
            [{"text": "Small", "source": "TITLE"}] * 2,
            "Small",
            "TITLE",
        ),
        (
            [
                {"text": "Small", "source": "TITLE"},
                {"text": "Tight", "source": "BODY"},
            ],
            "Small | Tight",
            "TITLE_AND_BODY",
        ),
    ],
)
def test_evidence_keeps_order_deduplication_and_source_defaults(
    spans, text, source
) -> None:
    result = {"extracted_facts": [{"fact_id": "F1", "evidence_spans": spans}]}

    item = build_semantic_review_view(result, "")["semantic_items"][0]

    assert item["item_id"] == "fact:F1"
    assert item["evidence_text"] == text
    assert item["evidence_source"] == source
    assert "_coverage_evidence" not in item


@pytest.mark.parametrize(
    ("fact_spans", "unit_evidence", "expected_text", "expected_source"),
    [
        ([{"text": "Fact", "source": "TITLE"}], "Unit", "Fact", "TITLE"),
        ([], "Unit", "Unit", "BODY"),
        ([], "", "Unknown", "COMMENT"),
    ],
)
def test_fact_fallback_and_handled_items_keep_existing_precedence(
    fact_spans, unit_evidence, expected_text, expected_source
) -> None:
    result = {
        "extracted_facts": [
            {"fact_id": "F1", "opinion": "事实观点", "evidence_spans": fact_spans}
        ],
        "fact_mappings": [
            {"fact_id": "F1", "label_codes": ["FIT_TOO_SMALL"], "reason": "映射原因"}
        ],
        "semantic_units": [
            {
                "fact_ids": ["F1"],
                "opinion": "单元观点",
                "evidence": unit_evidence,
                "evidence_source": "BODY",
                "label_code": "OTHER",
                "decision_reason": "单元原因",
            }
        ],
        "unknown_semantics": [
            {"fact_id": "F1", "evidence": "Unknown", "reason": "未知原因"}
        ],
    }

    view = build_semantic_review_view(result, "未使用的原文")

    assert len(view["semantic_items"]) == 1
    item = view["semantic_items"][0]
    assert item["evidence_text"] == expected_text
    assert item["evidence_source"] == expected_source
    assert item["opinion"] == "事实观点"
    assert item["label_code"] == "FIT_TOO_SMALL"
    assert item["reason"] == "映射原因"
    assert view["coverage_summary"]["complete"] is True
    assert view["unexplained_fragments"] == []


@pytest.mark.parametrize("with_taxonomy", [False, True])
def test_unknown_label_keeps_empty_path_without_changing_disposition(
    with_taxonomy, taxonomy
) -> None:
    result = {
        "semantic_units": [
            {"fact_id": "F1", "label_code": "UNKNOWN_LABEL", "evidence": "Covered"}
        ]
    }

    view = build_semantic_review_view(
        result, "Covered", taxonomy if with_taxonomy else None
    )

    assert view["semantic_items"][0]["label_path"] == []
    assert view["semantic_items"][0]["disposition"] == "MAPPED"
    assert view["coverage_summary"]["complete"] is True


def test_legacy_items_keep_order_and_coverage_cleanup() -> None:
    result = {
        "semantic_units": [
            {"fact_id": "U1", "label_code": "FIT_TOO_SMALL", "evidence": "Covered"}
        ],
        "unknown_semantics": [
            {"fact_id": "U2", "evidence": "Ignored", "disposition": "OUT_OF_SCOPE"}
        ],
    }
    before = deepcopy(result)

    view = build_semantic_review_view(result, "Covered. Ignored. Missing.")

    assert [item["item_id"] for item in view["semantic_items"]] == [
        "fact:U1",
        "fact:U2",
    ]
    assert all("_coverage_evidence" not in item for item in view["semantic_items"])
    assert view["unexplained_fragments"] == ["Missing"]
    assert view["coverage_summary"] == {
        "total": 2,
        "mapped": 1,
        "no_tag_needed": 1,
        "taxonomy_gap": 0,
        "true_ambiguity": 0,
        "analysis_failure": 0,
        "unexplained_fragment_count": 1,
        "complete": False,
    }
    assert result == before
