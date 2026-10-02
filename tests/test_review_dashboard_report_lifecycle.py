from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import test_insight_reports
from test_insight_reports import _complete_report
from test_result_version_reviews import _publish_review_required

from return_semantics.semantic_review import build_semantic_review_view
from web_backend.classification_result_service import ClassificationResultService
from web_backend.dashboard_service import DashboardConflict
from web_backend.review_label_corrections import apply_semantic_review_changes
from web_backend.review_service import (
    ReviewBatchConflict,
    ReviewService,
    RevisionConflict,
)


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    context, base = _publish_review_required(tmp_path)
    # 复用报告模型替身与配置构造器，让三个服务共享同一份待复核结果。
    with monkeypatch.context() as patch:
        patch.setattr(test_insight_reports, "_seed_result_context", lambda _: context)
        patch.setattr(test_insight_reports, "_publish", lambda _: base)
        _, dashboard, reports, captured = test_insight_reports._service_context(
            tmp_path
        )
    reviews = ReviewService(context.database)
    batch = reviews.create_batch(str(base["version_id"]), "user-1", "验证跨模块复核")
    return SimpleNamespace(
        database=context.database,
        base=base,
        results=ClassificationResultService(context.database),
        reviews=reviews,
        batch=batch,
        dashboard=dashboard,
        dashboards=reports.dashboard_service,
        reports=reports,
        captured=captured,
    )


def _publish_correction(lifecycle, item_adjustment=False):
    review = lifecycle.reviews.batch_records(lifecycle.batch["id"])["items"][0]
    details = {}
    if item_adjustment:
        item = review["classification"]["semantic_review"]["semantic_items"][0]
        details = {
            "action": "confirm",
            "semantic_item_reviews": [
                {
                    "semantic_item_id": item["item_id"],
                    "action": "change_label",
                    "label_code": "FIT_TOO_LARGE_U1",
                }
            ],
        }
    lifecycle.reviews.update_batch_record(
        batch_id=lifecycle.batch["id"],
        review_id=review["id"],
        expected_revision=review["revision"],
        actor_id="user-1",
        label_code=None if item_adjustment else "FIT_TOO_LARGE_U1",
        note="人工确认偏大，验证更正后的下游证据",
        **details,
    )
    return lifecycle.reviews.publish_batch(
        lifecycle.batch["id"],
        lifecycle.reviews.get_batch(lifecycle.batch["id"])["revision"],
        "user-1",
        "发布人工更正版本",
    )


def _advance_dashboard(lifecycle, derived):
    version_ids = [str(derived["version_id"])]
    plan = lifecycle.dashboards.preflight(version_ids, {})
    assert plan["ready"] is True
    assert plan["summary"]["pending_review_comment_count"] == 0
    assert plan["warnings"] == []
    return lifecycle.dashboards.create_version(
        lifecycle.dashboard["id"],
        expected_revision=lifecycle.dashboard["revision"],
        result_version_ids=version_ids,
        filters={},
        plan_hash=plan["plan_hash"],
        reason="使用人工更正结果",
        actor_id="user-1",
    )


def _assert_report_source(report, dashboard, result_id):
    assert report["status"] == "completed", report["error"]
    assert report["dashboard_id"] == dashboard["id"]
    assert report["dashboard_version_id"] == dashboard["version"]["version_id"]
    assert report["dashboard_version_no"] == dashboard["version"]["version"]
    assert (
        report["evidence"]["source"]["dashboard_version_id"]
        == (dashboard["version"]["version_id"])
    )
    assert [
        source["result_version_id"]
        for source in dashboard["version"]["source_snapshot"]
    ] == [result_id]


@pytest.mark.parametrize("item_adjustment", (False, True))
def test_review_publication_reaches_dashboard_and_report_without_snapshot_drift(
    lifecycle,
    item_adjustment,
):
    old_version = lifecycle.dashboard["version"]
    base_id = str(lifecycle.base["version_id"])
    old_records = lifecycle.results.records(base_id)
    old_report = _complete_report(lifecycle.dashboard, lifecycle.reports)
    _assert_report_source(old_report, lifecycle.dashboard, base_id)
    assert old_version["summary"]["record_count"] == 0
    assert old_version["summary"]["pending_review_record_count"] == 2
    assert [issue["id"] for issue in old_report["content"]["issues"]] == [
        "issue.scope.coverage"
    ]

    derived = _publish_correction(lifecycle, item_adjustment)
    current = _advance_dashboard(lifecycle, derived)
    report = _complete_report(current, lifecycle.reports)
    _assert_report_source(report, current, derived["version_id"])
    assert derived["version"] == current["version"]["version"] == 2
    assert derived["parent_version_id"] == base_id
    assert derived["source_review_batch_id"] == lifecycle.batch["id"]
    assert derived["changed_unit_count"] == 1
    assert derived["inherited_unit_count"] == 0
    assert current["version"]["summary"]["review_changed_unit_count"] == 1
    assert current["version"]["summary"]["record_count"] == 2
    assert (
        current["version"]["source_snapshot"][0]["result_version_id"]
        == (derived["version_id"])
    )
    assert lifecycle.dashboards.get(current["id"])["version"] == current["version"]
    issue = report["content"]["issues"][0]
    assert issue["id"] == "issue.reason.FIT_TOO_LARGE_U1"
    assert issue["metrics"]["matched_return_samples"] == 2
    assert issue["metrics"]["return_sample_share"] == 100.0
    assert "reason.FIT_TOO_LARGE_U1" in issue["evidence_ids"]
    assert "reason.FIT_TOO_SMALL_U1" not in report["evidence"]["catalog"]
    assert report["evidence"]["analysis"]["diagnostics"][0]["reason_code"] == (
        "FIT_TOO_LARGE_U1"
    )
    assert (
        issue["evidence_ids"]
        == (report["evidence"]["blueprint"]["issues"][0]["evidence_ids"])
    )
    request = json.loads(lifecycle.captured["messages"][1]["content"])
    assert request["fixed_blueprint"]["issues"][0]["id"] == issue["id"]
    assert lifecycle.results.records(base_id) == old_records
    assert (
        lifecycle.dashboards.get(current["id"], old_version["version_id"])["version"]
        == old_version
    )
    assert lifecycle.reports.get(old_report["id"]) == old_report
    assert [
        item["id"]
        for item in lifecycle.reports.list(
            current["id"], current["version"]["version_id"]
        )
    ] == [report["id"]]
    _assert_publication_audits(lifecycle, derived, current, report)


def _assert_publication_audits(lifecycle, derived, dashboard, report):
    targets = (
        ("review_batch", lifecycle.batch["id"], "publish"),
        ("analysis_dashboard", dashboard["id"], "create_version"),
        ("ai_insight_report", report["id"], "create"),
    )
    with lifecycle.database.connect() as connection:
        audits = [
            connection.execute(
                "SELECT actor_id, after_json FROM audit_logs "
                "WHERE entity_type = ? AND entity_id = ? AND action = ?",
                target,
            ).fetchone()
            for target in targets
        ]
    assert all(audit is not None and audit["actor_id"] == "user-1" for audit in audits)
    review, board, generation = [json.loads(audit["after_json"]) for audit in audits]
    assert review["result_version_id"] == derived["version_id"]
    assert board["version_id"] == dashboard["version"]["version_id"]
    assert generation["dashboard_version_id"] == board["version_id"]


@pytest.mark.parametrize("fact_ids", ([], ["F1"], ["F1", "F2"]))
def test_item_label_correction_preserves_other_facts_and_audit(lifecycle, fact_ids):
    record = lifecycle.reviews.batch_records(lifecycle.batch["id"])["items"][0]
    classification = deepcopy(record["classification"])
    unit = classification["semantic_units"][0]
    unit.update(fact_id=fact_ids[0] if fact_ids else None, fact_ids=fact_ids)
    classification["semantic_units"].append(
        {**unit, "opinion": "第二个独立观点", "fact_id": None, "fact_ids": []}
    )
    classification["fact_mappings"] = [
        {"fact_id": fact_id, "label_codes": [unit["label_code"]]}
        for fact_id in fact_ids
    ]
    item_id = build_semantic_review_view({"semantic_units": [unit]}, "")[
        "semantic_items"
    ][0]["item_id"]
    classification["human_semantic_reviews"] = [
        {
            "semantic_item_id": item_id,
            "action": "change_label",
            "label_code": "FIT_TOO_LARGE_U1",
            "assessed_by": "user-1",
        }
    ]
    before = deepcopy(classification)
    taxonomy = lifecycle.reviews.standard_service.taxonomy_config_for_result_version(
        lifecycle.base["version_id"]
    )
    corrected = apply_semantic_review_changes(classification, taxonomy)
    assert classification == before
    assert (
        corrected["human_semantic_reviews"][0].items()
        >= before["human_semantic_reviews"][0].items()
    )
    assert corrected["human_semantic_reviews"][0]["applied"] is True
    assert apply_semantic_review_changes(corrected, taxonomy) == corrected
    assert corrected["semantic_units"][0]["label_code"] == "FIT_TOO_LARGE_U1"
    assert corrected["semantic_units"][-1] == before["semantic_units"][-1]
    assert set(corrected["problem_label_codes"]) == {
        "FIT_TOO_SMALL_U1",
        "FIT_TOO_LARGE_U1",
    }
    assert corrected["positive_label_codes"] == []
    assert set(corrected["comment_summary"]["negative_label_codes"]) == set(
        corrected["problem_label_codes"]
    )
    if fact_ids:
        assert corrected["fact_mappings"][0]["label_codes"] == ["FIT_TOO_LARGE_U1"]
    if len(fact_ids) == 2:
        assert corrected["semantic_units"][1]["fact_ids"] == ["F2"]
        assert corrected["semantic_units"][1]["label_code"] == "FIT_TOO_SMALL_U1"
        assert corrected["fact_mappings"][1] == before["fact_mappings"][1]


@pytest.mark.parametrize("conflict", ("pending", "stale_revision"))
def test_blocked_review_does_not_create_downstream_versions(lifecycle, conflict):
    revision = lifecycle.batch["revision"]
    error = ReviewBatchConflict if conflict == "pending" else RevisionConflict
    message = "未完成" if conflict == "pending" else "其他用户修改"
    if conflict == "stale_revision":
        revision += 1
    with pytest.raises(error, match=message):
        lifecycle.reviews.publish_batch(
            lifecycle.batch["id"], revision, "user-1", "拒绝无效发布"
        )
    assert lifecycle.reviews.get_batch(lifecycle.batch["id"])["status"] == "draft"
    assert (
        lifecycle.results.history(str(lifecycle.base["version_id"]))[0]["version"] == 1
    )
    assert (
        lifecycle.dashboards.get(lifecycle.dashboard["id"])["version"]
        == (lifecycle.dashboard["version"])
    )
    with lifecycle.database.connect() as connection:
        counts = [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "classification_result_versions",
                "dashboard_versions",
                "ai_insight_reports",
                "ai_insight_report_versions",
            )
        ]
    assert counts == [1, 1, 0, 0]


def test_dashboard_conflict_after_review_keeps_current_report_scope(lifecycle):
    derived = _publish_correction(lifecycle)
    version_ids = [str(derived["version_id"])]
    plan = lifecycle.dashboards.preflight(version_ids, {})
    current = _advance_dashboard(lifecycle, derived)
    with pytest.raises(DashboardConflict, match="其他用户更新"):
        lifecycle.dashboards.create_version(
            current["id"],
            expected_revision=lifecycle.dashboard["revision"],
            result_version_ids=version_ids,
            filters={},
            plan_hash=plan["plan_hash"],
            reason="拒绝并发覆盖",
            actor_id="user-1",
        )
    assert [
        version["version"] for version in lifecycle.dashboards.versions(current["id"])
    ] == [2, 1]
    assert lifecycle.dashboards.get(current["id"])["version"] == current["version"]
    report = _complete_report(current, lifecycle.reports)
    _assert_report_source(report, current, derived["version_id"])


def test_failed_report_retry_uses_original_scope_after_review_publication(
    lifecycle,
    monkeypatch,
):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("合成模型暂时不可用")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.reports.client_factory, "generate_json", unavailable)
        failed = _complete_report(lifecycle.dashboard, lifecycle.reports)
    assert failed["status"] == "failed"
    assert failed["version_no"] is None
    derived = _publish_correction(lifecycle)
    current = _advance_dashboard(lifecycle, derived)
    retried = lifecycle.reports.retry(failed["id"], "user-1")
    assert retried["parent_job_id"] == failed["id"]
    assert retried["attempt_no"] == 2
    assert lifecycle.reports.claim_next() == retried["id"]
    lifecycle.reports.run(retried["id"])
    completed = lifecycle.reports.get(retried["id"])
    _assert_report_source(completed, lifecycle.dashboard, lifecycle.base["version_id"])
    assert completed["content"]["issues"][0]["id"] == "issue.scope.coverage"
    assert completed["evidence"] == failed["evidence"]
    assert completed["version_no"] == 1
    latest = _complete_report(current, lifecycle.reports)
    _assert_report_source(latest, current, derived["version_id"])
    assert latest["content"]["issues"][0]["id"] == "issue.reason.FIT_TOO_LARGE_U1"
    assert latest["version_no"] == 2
    assert lifecycle.reports.get(failed["id"])["status"] == "failed"
    with lifecycle.database.connect() as connection:
        audit = connection.execute(
            "SELECT after_json FROM audit_logs "
            "WHERE entity_type = 'ai_insight_report' AND entity_id = ? "
            "AND action = 'retry'",
            (failed["id"],),
        ).fetchone()
    assert json.loads(audit["after_json"]) == {"new_job_id": retried["id"]}


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


@pytest.mark.parametrize("operation", ["remove", "no_tag_needed", "add", "unknown"])
def test_item_operations_reach_published_results_dashboard_and_report(
    lifecycle, operation
):
    record, classification, taxonomy = _projection_context(lifecycle)
    details = {}
    if operation == "unknown":
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
                "action": "change_label",
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
    base_id = lifecycle.base["version_id"]
    before = lifecycle.results.records(base_id)
    lifecycle.reviews.update_batch_record(
        lifecycle.batch["id"],
        record["id"],
        record["revision"],
        "user-1",
        None,
        "合成逐项处置",
        action="confirm",
        **details,
    )
    derived = lifecycle.reviews.publish_batch(
        lifecycle.batch["id"],
        lifecycle.reviews.get_batch(lifecycle.batch["id"])["revision"],
        "user-1",
        "发布合成处置",
    )
    published = lifecycle.results.records(derived["version_id"])["items"][0][
        "classification"
    ]
    codes = {unit["label_code"] for unit in published["semantic_units"]}
    assert codes == (
        {"FIT_TOO_SMALL_U1", "FIT_TOO_LARGE_U1"}
        if operation == "add"
        else {"FIT_TOO_LARGE_U1"}
        if operation == "unknown"
        else set()
    )
    assert published["comment_summary"]["status"] == (
        "NEGATIVE" if codes else "NO_CONFIRMED"
    )
    assert lifecycle.results.records(base_id) == before
    assert (
        apply_semantic_review_changes(published, taxonomy, record["comment"])
        == published
    )
    assert (
        build_semantic_review_view(published, record["comment"])[
            "unexplained_fragments"
        ]
        == []
    )
    if operation == "no_tag_needed":
        assert published["unknown_semantics"][0]["disposition"] == "EXPECTED_ABSTENTION"
    assert derived["changed_unit_count"] == 1
    with pytest.raises(ReviewBatchConflict, match="发布"):
        lifecycle.reviews.publish_batch(
            lifecycle.batch["id"],
            lifecycle.reviews.get_batch(lifecycle.batch["id"])["revision"],
            "user-1",
            "重复发布",
        )
    current = _advance_dashboard(lifecycle, derived)
    assert current["version"]["summary"]["record_count"] == 2
    assert current["version"]["summary"]["review_changed_unit_count"] == 1
    report = _complete_report(current, lifecycle.reports)
    _assert_report_source(report, current, derived["version_id"])
    reason_ids = {
        key.removeprefix("reason.")
        for key in report["evidence"]["catalog"]
        if key.startswith("reason.")
    }
    assert reason_ids == codes


@pytest.mark.parametrize("action", ["remove", "no_tag_needed"])
def test_partial_merged_fact_disposal_preserves_other_fact(lifecycle, action):
    record, classification, taxonomy = _projection_context(lifecycle)
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


def test_mixed_disposal_and_positive_addition_recalculate_summary(lifecycle):
    record, classification, taxonomy = _projection_context(lifecycle)
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


def test_ambiguous_addition_requires_valid_direction_without_partial_write(lifecycle):
    record, _classification, taxonomy = _projection_context(lifecycle)
    label = next(
        label for label in taxonomy.labels if len(label.allowed_sentiments) > 1
    )
    added = {
        "evidence_text": record["comment"],
        "opinion": "合成待定方向",
        "label_code": label.code,
    }
    with pytest.raises(ValueError, match="选择评价方向"):
        lifecycle.reviews.update_batch_record(
            lifecycle.batch["id"],
            record["id"],
            record["revision"],
            "user-1",
            None,
            "缺少方向",
            action="confirm",
            added_semantic_items=[added],
        )
    assert lifecycle.reviews.get(record["id"])["revision"] == record["revision"]
    with lifecycle.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM review_revisions").fetchone()[0]
            == 0
        )
    updated = lifecycle.reviews.update_batch_record(
        lifecycle.batch["id"],
        record["id"],
        record["revision"],
        "user-1",
        None,
        "明确评价方向",
        action="confirm",
        added_semantic_items=[{**added, "sentiment": str(label.allowed_sentiments[0])}],
    )
    assert updated["revision"] == record["revision"] + 1


def test_same_label_review_does_not_split_merged_unit(lifecycle):
    record, classification, taxonomy = _projection_context(lifecycle)
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


def test_whole_label_change_and_addition_both_survive_publication(lifecycle):
    record, _classification, _taxonomy = _projection_context(lifecycle)
    lifecycle.reviews.update_batch_record(
        lifecycle.batch["id"],
        record["id"],
        record["revision"],
        "user-1",
        "FIT_TOO_LARGE_U1",
        "合成整条更正并补录",
        action="modify",
        added_semantic_items=[
            {
                "evidence_text": record["comment"],
                "opinion": "另一个合成观点",
                "label_code": "FIT_TOO_SMALL_U1",
            }
        ],
    )
    derived = lifecycle.reviews.publish_batch(
        lifecycle.batch["id"],
        lifecycle.reviews.get_batch(lifecycle.batch["id"])["revision"],
        "user-1",
        "发布合成混合操作",
    )
    units = lifecycle.results.records(derived["version_id"])["items"][0][
        "classification"
    ]["semantic_units"]
    assert [unit["label_code"] for unit in units] == [
        "FIT_TOO_LARGE_U1",
        "FIT_TOO_SMALL_U1",
    ]
