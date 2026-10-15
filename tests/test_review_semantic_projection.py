"""人工修正共享语义投影的独立回归，不调用批次写入口。"""

import json
from copy import deepcopy

import pytest
from historical_review_fixtures import historical_batch
from test_review_dashboard_report_lifecycle import lifecycle as lifecycle

from return_semantics.semantic_review import build_semantic_review_view
from web_backend.review_label_corrections import apply_semantic_review_changes
from web_backend.review_service import ReviewService


@pytest.fixture
def projection_lifecycle(lifecycle):
    lifecycle.batch = historical_batch(lifecycle.context, lifecycle.base)
    lifecycle.reviews = ReviewService(lifecycle.database)
    return lifecycle


def _projection_context(lifecycle):
    record = lifecycle.reviews.batch_records(lifecycle.batch["id"])["items"][0]
    with lifecycle.database.connect() as connection:
        row = connection.execute(
            "SELECT classification_json FROM review_records WHERE id = ?",
            (record["id"],),
        ).fetchone()
    taxonomy = lifecycle.reviews.standard_service.taxonomy_config_for_result_version(
        lifecycle.base["version_id"]
    )
    return record, json.loads(row[0]), taxonomy


def _prepare_item_operation(lifecycle, operation):
    record, classification, taxonomy = _projection_context(lifecycle)
    details = {}
    if operation in {"unknown", "diagnostic_change", "diagnostic_no_tag"}:
        unit = classification["semantic_units"][0]
        classification.update(
            semantic_units=[],
            primary_label_codes=[],
            problem_label_codes=[],
            unknown_semantics=[
                {
                    "opinion": unit["opinion"],
                    "evidence": unit["evidence"],
                    "reason": "合成未知项",
                    "disposition": "TAXONOMY_GAP",
                }
            ],
        )
        if operation.startswith("diagnostic"):
            classification.update(
                unknown_semantics=[],
                review_reasons=[],
                review_diagnostics=[
                    {
                        "code": "LABEL_RULE_REVIEW_REQUIRED",
                        "evidence_text": unit["evidence"],
                        "detail": "合成标签规则要求人工判断",
                    }
                ],
            )
        with lifecycle.database.transaction() as connection:
            for table, predicate, identity in [
                ("review_records", "id = ?", record["id"]),
                (
                    "classification_units",
                    "result_version_id = ?",
                    lifecycle.base["version_id"],
                ),
            ]:
                connection.execute(
                    f"UPDATE {table} SET classification_json = ? WHERE {predicate}",
                    (json.dumps(classification), identity),
                )
        details["semantic_item_reviews"] = [
            {
                "semantic_item_id": build_semantic_review_view(
                    classification, record["comment"]
                )["semantic_items"][0]["item_id"],
                "action": (
                    "no_tag_needed"
                    if operation == "diagnostic_no_tag"
                    else "change_label"
                ),
                "label_code": "FIT_TOO_LARGE_U1",
            }
        ]
    elif operation == "add":
        details["added_semantic_items"] = [
            {
                "item_id": "manual-1",
                "evidence_text": record["comment"],
                "opinion": "合成补录观点",
                "label_code": "FIT_TOO_LARGE_U1",
            }
        ]
    else:
        details["semantic_item_reviews"] = [
            {
                "semantic_item_id": record["classification"]["semantic_review"][
                    "semantic_items"
                ][0]["item_id"],
                "action": operation,
            }
        ]
    return record, details, taxonomy


@pytest.mark.parametrize("action", ["change_label", "no_tag_needed"])
@pytest.mark.parametrize("evidence", ["", "原文中不存在的合成诊断证据"])
def test_diagnostic_projection_requires_original_comment_evidence(
    projection_lifecycle, action, evidence
):
    _prepare_item_operation(projection_lifecycle, "diagnostic_change")
    record, classification, taxonomy = _projection_context(projection_lifecycle)
    classification["review_diagnostics"][0]["evidence_text"] = evidence
    item = build_semantic_review_view(classification, record["comment"])[
        "semantic_items"
    ][0]
    classification["human_semantic_reviews"] = [
        {
            "semantic_item_id": item["item_id"],
            "action": action,
            "label_code": "FIT_TOO_LARGE_U1",
        }
    ]
    before = deepcopy(classification)
    with pytest.raises(ValueError, match="原文证据"):
        apply_semantic_review_changes(classification, taxonomy, record["comment"])
    assert classification == before


@pytest.mark.parametrize("action", ["remove", "no_tag_needed"])
def test_partial_merged_fact_disposal_preserves_other_fact(
    projection_lifecycle, action
):
    record, classification, taxonomy = _projection_context(projection_lifecycle)
    from return_semantics.schemas import ExtractedFact

    unit = classification["semantic_units"][0]
    unit.update(fact_id="F1", fact_ids=["F1", "F2"])
    classification["extracted_facts"] = [
        ExtractedFact.model_validate(
            {
                **{
                    key: value
                    for key, value in unit.items()
                    if key in ExtractedFact.model_fields
                },
                "fact_id": fact_id,
                "evidence_spans": [{"text": unit["evidence"], "source": "COMMENT"}],
            }
        ).model_dump(mode="json")
        for fact_id in ("F1", "F2")
    ]
    classification["fact_mappings"] = [
        {"fact_id": fact_id, "label_codes": [unit["label_code"]]}
        for fact_id in ("F1", "F2")
    ]
    classification["human_semantic_reviews"] = [
        {"semantic_item_id": "fact:F1", "action": action}
    ]
    projected = apply_semantic_review_changes(
        classification, taxonomy, record["comment"]
    )
    assert projected["semantic_units"][0]["fact_ids"] == ["F2"]
    assert projected["problem_label_codes"] == [unit["label_code"]]
    assert {fact["fact_id"] for fact in projected["extracted_facts"]} == (
        {"F2"} if action == "remove" else {"F1", "F2"}
    )
    assert projected["fact_mappings"][-1] == classification["fact_mappings"][-1]
    if action == "no_tag_needed":
        assert projected["fact_mappings"][0]["disposition"] == "EXPECTED_ABSTENTION"
        assert projected["unknown_semantics"][0]["fact_id"] == "F1"


def test_mixed_disposal_and_positive_addition_recalculate_summary(projection_lifecycle):
    record, classification, taxonomy = _projection_context(projection_lifecycle)
    positive = next(
        label for label in taxonomy.labels if "POSITIVE" in label.allowed_sentiments
    )
    item_id = build_semantic_review_view(classification, record["comment"])[
        "semantic_items"
    ][0]["item_id"]
    classification["human_semantic_reviews"] = [
        {"semantic_item_id": item_id, "action": "remove"}
    ]
    classification["human_added_semantic_items"] = [
        {
            "evidence_text": record["comment"],
            "opinion": "合成正面补录",
            "label_code": positive.code,
            "sentiment": "POSITIVE",
        }
    ]
    projected = apply_semantic_review_changes(
        classification, taxonomy, record["comment"]
    )
    assert projected["problem_label_codes"] == []
    assert projected["positive_label_codes"] == [positive.code]
    assert projected["comment_summary"]["status"] == "POSITIVE"
    assert (
        len(build_semantic_review_view(projected, record["comment"])["semantic_items"])
        == 1
    )
    projected["human_added_semantic_items"] = [
        {
            "item_id": "manual-1",
            "evidence_text": record["comment"],
            "opinion": "下一次合成补录",
            "label_code": "FIT_TOO_LARGE_U1",
        }
    ]
    next_result = apply_semantic_review_changes(projected, taxonomy, record["comment"])
    assert len(next_result["semantic_units"]) == 2
    assert next_result["comment_summary"]["status"] == "MIXED"
    assert len({unit["fact_id"] for unit in next_result["semantic_units"]}) == 2


def test_same_label_review_does_not_split_merged_unit(projection_lifecycle):
    record, classification, taxonomy = _projection_context(projection_lifecycle)
    classification["semantic_units"][0].update(fact_id="F1", fact_ids=["F1", "F2"])
    classification["human_semantic_reviews"] = [
        {
            "semantic_item_id": "fact:F1",
            "action": "change_label",
            "label_code": classification["semantic_units"][0]["label_code"],
        }
    ]
    projected = apply_semantic_review_changes(
        classification, taxonomy, record["comment"]
    )
    assert projected["semantic_units"] == classification["semantic_units"]
