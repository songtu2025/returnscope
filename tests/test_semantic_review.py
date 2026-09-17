from return_semantics.semantic_review import (
    build_semantic_review_view,
    requires_business_review,
)


def test_builds_review_items_from_facts_and_mappings(taxonomy) -> None:
    result = {
        "extracted_facts": [
            {
                "fact_id": "F1",
                "opinion": "尺码偏小",
                "evidence_spans": [
                    {"text": "Too small", "source": "COMMENT"},
                ],
            },
            {
                "fact_id": "F2",
                "opinion": "送货很快",
                "evidence_spans": [
                    {"text": "delivery was quick", "source": "COMMENT"},
                ],
            },
        ],
        "fact_mappings": [
            {"fact_id": "F1", "label_codes": ["FIT_TOO_SMALL"]},
            {
                "fact_id": "F2",
                "label_codes": [],
                "disposition": "OUT_OF_SCOPE",
                "reason": "当前分类范围外",
            },
        ],
        "semantic_units": [],
        "unknown_semantics": [],
    }

    view = build_semantic_review_view(
        result,
        "Too small, delivery was quick.",
        taxonomy,
    )

    mapped, ignored = view["semantic_items"]
    assert mapped["item_id"] == "fact:F1"
    assert mapped["evidence_text"] == "Too small"
    assert mapped["opinion"] == "尺码偏小"
    assert mapped["label_code"] == "FIT_TOO_SMALL"
    assert mapped["label_path"][-1] == "偏小"
    assert mapped["disposition"] == "MAPPED"
    assert ignored == {
        "item_id": "fact:F2",
        "fact_id": "F2",
        "evidence_text": "delivery was quick",
        "evidence_source": "COMMENT",
        "opinion": "送货很快",
        "label_code": "",
        "label_path": [],
        "disposition": "NO_TAG_NEEDED",
        "reason": "当前分类范围外",
    }
    assert view["coverage_summary"] == {
        "total": 2,
        "mapped": 1,
        "no_tag_needed": 1,
        "taxonomy_gap": 0,
        "true_ambiguity": 0,
        "analysis_failure": 0,
        "unexplained_fragment_count": 0,
        "complete": True,
    }


def test_expected_abstention_stays_visible_without_business_review(taxonomy) -> None:
    result = {
        "status": "AUTO_APPROVED",
        "extracted_facts": [
            {
                "fact_id": "F1",
                "opinion": "触屏可能不灵敏",
                "evidence_spans": [{"text": "touch response might be limited"}],
            }
        ],
        "fact_mappings": [
            {
                "fact_id": "F1",
                "candidate_label_codes": ["FIT_TOO_SMALL"],
                "disposition": "EXPECTED_ABSTENTION",
                "reason": "原文命题不确定",
            }
        ],
        "unknown_semantics": [
            {
                "fact_id": "F1",
                "opinion": "触屏可能不灵敏",
                "evidence": "touch response might be limited",
                "disposition": "EXPECTED_ABSTENTION",
                "reason": "原文命题不确定",
            }
        ],
    }

    view = build_semantic_review_view(
        result,
        "touch response might be limited",
        taxonomy,
    )

    assert view["semantic_items"][0]["disposition"] == "NO_TAG_NEEDED"
    assert requires_business_review(result, "touch response might be limited") is False


def test_separates_unknown_causes_and_unexplained_text() -> None:
    result = {
        "extracted_facts": [],
        "fact_mappings": [],
        "semantic_units": [],
        "unknown_semantics": [
            {
                "opinion": "耐用性概念暂无标签",
                "evidence": "durability is unusual",
                "evidence_source": "BODY",
                "reason": "现有标签体系未覆盖",
                "disposition": "TAXONOMY_GAP",
            },
            {
                "opinion": "无法确定所指商品",
                "evidence": "it is odd",
                "evidence_source": "BODY",
                "reason": "代词缺少先行词",
                "disposition": "MAPPING_UNCERTAIN",
            },
        ],
    }

    view = build_semantic_review_view(
        result,
        "durability is unusual. it is odd. Also arrived late.",
    )

    assert [item["disposition"] for item in view["semantic_items"]] == [
        "TAXONOMY_GAP",
        "TRUE_AMBIGUITY",
    ]
    assert view["unexplained_fragments"] == ["Also arrived late"]
    assert view["coverage_summary"]["complete"] is False


def test_model_error_is_not_reported_as_unknown_semantic() -> None:
    view = build_semantic_review_view(
        {
            "status": "MODEL_ERROR",
            "review_reasons": ["请求超时"],
        },
        "Too small",
    )

    assert view["semantic_items"][0]["disposition"] == "ANALYSIS_FAILURE"
    assert view["semantic_items"][0]["reason"] == "请求超时"
    assert view["semantic_items"][0]["diagnostic_domain"] == "TECHNICAL_RUNTIME"
    assert view["semantic_items"][0]["diagnostic_code"] == "MODEL_RUN_TIMEOUT"
    assert view["semantic_items"][0]["business_review_required"] is False
    assert view["coverage_summary"]["analysis_failure"] == 1
    assert view["coverage_summary"]["complete"] is False


def test_item_id_is_stable_for_legacy_semantic_unit() -> None:
    result = {
        "semantic_units": [
            {
                "opinion": "尺码偏小",
                "label_code": "FIT_TOO_SMALL",
                "evidence": "Too small",
                "evidence_source": "COMMENT",
            }
        ]
    }

    first = build_semantic_review_view(result, "Too small")
    second = build_semantic_review_view(result, "Too small")

    assert (
        first["semantic_items"][0]["item_id"] == second["semantic_items"][0]["item_id"]
    )


def test_structured_facts_do_not_create_lexical_gap_noise() -> None:
    result = {
        "status": "AUTO_APPROVED",
        "extracted_facts": [
            {
                "fact_id": "F1",
                "opinion": "手套保暖",
                "evidence_spans": [
                    {"text": "These gloves are warm", "source": "BODY"},
                ],
            }
        ],
        "fact_mappings": [
            {"fact_id": "F1", "label_codes": ["FIT_TOO_SMALL"]},
        ],
        "semantic_units": [],
        "unknown_semantics": [],
    }

    view = build_semantic_review_view(
        result,
        "标题：Warm winter gloves\n内容：These gloves are warm because of the lining.",
    )

    assert view["unexplained_fragments"] == []
    assert view["coverage_summary"]["complete"] is True


def test_system_review_reason_is_exposed_without_primary_noise() -> None:
    result = {
        "status": "MANUAL_REVIEW",
        "review_reasons": [
            "多个问题但主因不明确",
            "模型要求复核",
            "覆盖审计失败，可能存在未抽取事实，需人工复核",
        ],
        "extracted_facts": [
            {
                "fact_id": "F1",
                "opinion": "手套保暖",
                "evidence_spans": [
                    {"text": "These gloves are warm", "source": "BODY"},
                ],
            }
        ],
        "fact_mappings": [
            {"fact_id": "F1", "label_codes": ["FIT_TOO_SMALL"]},
        ],
    }

    view = build_semantic_review_view(result, "These gloves are warm.")

    failure = view["semantic_items"][-1]
    assert failure["disposition"] == "ANALYSIS_FAILURE"
    assert failure["opinion"] == "可能存在用户反馈漏抽"
    assert failure["reason"] == "覆盖审计失败，可能存在未抽取事实，需人工复核"
    assert failure["diagnostic_domain"] == "SEMANTIC_ANALYSIS_QUALITY"
    assert failure["diagnostic_code"] == "COVERAGE_AUDIT_FAILED"
    assert failure["detail_status"] == "NOT_RETAINED"
    assert "未保留疑似漏抽的原文片段" in failure["action"]
    assert failure["business_review_required"] is False
    assert view["coverage_summary"]["analysis_failure"] == 1
    assert view["coverage_summary"]["complete"] is False


def test_primary_only_review_reason_does_not_create_system_failure() -> None:
    result = {
        "status": "MANUAL_REVIEW",
        "review_reasons": ["多个问题但主因不明确", "模型要求复核"],
        "extracted_facts": [
            {
                "fact_id": "F1",
                "opinion": "手套保暖",
                "evidence_spans": [
                    {"text": "These gloves are warm", "source": "BODY"},
                ],
            }
        ],
        "fact_mappings": [
            {"fact_id": "F1", "label_codes": ["FIT_TOO_SMALL"]},
        ],
    }

    view = build_semantic_review_view(result, "These gloves are warm.")

    assert view["coverage_summary"]["analysis_failure"] == 0
    assert view["coverage_summary"]["complete"] is True


def test_each_system_failure_has_its_own_actionable_diagnostic() -> None:
    result = {
        "status": "MANUAL_REVIEW",
        "review_reasons": [
            "两次模型的语义结果不一致",
            "二次模型调用失败: 请求超时",
        ],
    }

    view = build_semantic_review_view(result, "These gloves are warm.")

    mismatch, timeout = view["semantic_items"]
    assert mismatch["diagnostic_code"] == "MODEL_RESULT_MISMATCH"
    assert mismatch["detail_status"] == "NOT_RETAINED"
    assert "未保留两次模型的差异明细" in mismatch["action"]
    assert timeout["diagnostic_code"] == "SECONDARY_MODEL_TIMEOUT"
    assert timeout["diagnostic_domain"] == "TECHNICAL_RUNTIME"
    assert timeout["detail_status"] == "NOT_APPLICABLE"
    assert timeout["action"] == "无需业务员核验；请系统重试风险复核。"
    assert all(
        item["disposition"] == "ANALYSIS_FAILURE" for item in view["semantic_items"]
    )
    assert view["coverage_summary"]["true_ambiguity"] == 0
    assert view["coverage_summary"]["analysis_failure"] == 2


def test_structured_diagnostic_is_preferred_over_legacy_reason() -> None:
    result = {
        "status": "MANUAL_REVIEW",
        "review_reasons": ["两次模型的语义结果不一致"],
        "review_diagnostics": [
            {
                "code": "MODEL_RESULT_MISMATCH",
                "evidence_text": "warm without bulk",
                "primary_result": "保暖",
                "secondary_result": "保暖、轻便",
                "detail": "风险复核比首次分析多提取了轻便",
                "action": "请业务员核对是否应保留轻便标签。",
            }
        ],
    }

    view = build_semantic_review_view(result, "warm without bulk")

    assert len(view["semantic_items"]) == 1
    diagnostic = view["semantic_items"][0]
    assert diagnostic["diagnostic_code"] == "MODEL_RESULT_MISMATCH"
    assert diagnostic["detail_status"] == "AVAILABLE"
    assert diagnostic["evidence_text"] == "warm without bulk"
    assert diagnostic["primary_result"] == "保暖"
    assert diagnostic["secondary_result"] == "保暖、轻便"
    assert diagnostic["detail"] == "风险复核比首次分析多提取了轻便"
    assert diagnostic["business_review_required"] is True
    assert diagnostic["action"] == "请业务员核对是否应保留轻便标签。"


def test_structured_system_rerun_is_not_assigned_to_business() -> None:
    result = {
        "status": "MANUAL_REVIEW",
        "review_diagnostics": [
            {
                "code": "MODEL_RESULT_MISMATCH",
                "evidence_text": "warm without bulk",
                "primary_result": "保暖",
                "secondary_result": "保暖、轻便",
                "detail": "复核结果多出轻便",
                "action": "SYSTEM_RERUN",
            }
        ],
    }

    diagnostic = build_semantic_review_view(result, "warm without bulk")[
        "semantic_items"
    ][0]

    assert diagnostic["detail_status"] == "AVAILABLE"
    assert diagnostic["business_review_required"] is False
    assert diagnostic["action"] == (
        "无需业务员判断本次运行异常；请系统重跑，差异明细仅用于定位。"
    )
    assert requires_business_review(result, "warm without bulk") is False


def test_true_ambiguity_is_assigned_to_business_review() -> None:
    result = {
        "status": "UNKNOWN_SEMANTIC",
        "extracted_facts": [
            {
                "fact_id": "F1",
                "opinion": "触屏表现有限制",
                "evidence_spans": [{"text": "touchscreen was inconsistent"}],
            }
        ],
        "fact_mappings": [
            {
                "fact_id": "F1",
                "label_codes": [],
                "disposition": "MAPPING_UNCERTAIN",
            }
        ],
    }

    assert requires_business_review(result, "touchscreen was inconsistent") is True


def test_model_error_without_extracted_facts_is_not_assigned_to_business() -> None:
    result = {
        "status": "MODEL_ERROR",
        "review_reasons": ["请求超时"],
        "review_diagnostics": [
            {
                "code": "MODEL_RUN_TIMEOUT",
                "detail": "请求超时",
                "action": "SYSTEM_RERUN",
            }
        ],
    }

    assert requires_business_review(result, "Too small") is False


def test_accepts_enriched_result_shape_with_ignored_semantics() -> None:
    result = {
        "status": "AUTO_APPROVED",
        "facts": [
            {
                "fact_id": "F1",
                "opinion": "配送很快",
                "evidence_spans": [
                    {"text": "delivery was quick", "source": "BODY"},
                ],
            }
        ],
        "fact_mappings": [
            {
                "fact_id": "F1",
                "label_codes": [],
                "disposition": "OUT_OF_SCOPE",
                "reason": "物流信息不属于商品反馈标签",
            }
        ],
        "ignored_semantics": [
            {
                "fact_id": "F1",
                "opinion": "配送很快",
                "evidence": "delivery was quick",
                "disposition": "OUT_OF_SCOPE",
                "reason": "物流信息不属于商品反馈标签",
            }
        ],
    }

    view = build_semantic_review_view(result, "delivery was quick")

    assert view["coverage_summary"]["no_tag_needed"] == 1
    assert view["coverage_summary"]["complete"] is True
