from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import test_insight_reports
from test_insight_reports import _complete_report
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_service import ClassificationResultService
from web_backend.dashboard_service import DashboardConflict
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


def _publish_correction(lifecycle):
    review = lifecycle.reviews.batch_records(lifecycle.batch["id"])["items"][0]
    lifecycle.reviews.update_batch_record(
        batch_id=lifecycle.batch["id"],
        review_id=review["id"],
        expected_revision=review["revision"],
        actor_id="user-1",
        label_code="FIT_TOO_LARGE_U1",
        note="人工确认偏大，验证更正后的下游证据",
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


def test_review_publication_reaches_dashboard_and_report_without_snapshot_drift(
    lifecycle,
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

    derived = _publish_correction(lifecycle)
    current = _advance_dashboard(lifecycle, derived)
    report = _complete_report(current, lifecycle.reports)
    _assert_report_source(report, current, derived["version_id"])
    assert derived["version"] == current["version"]["version"] == 2
    assert derived["parent_version_id"] == base_id
    assert derived["source_review_batch_id"] == lifecycle.batch["id"]
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
