from __future__ import annotations

from pathlib import Path

import pytest
from test_dashboard_versions import _create_dashboard, _ready_result

from web_backend import dashboard_insight_overview


@pytest.mark.parametrize("analysis_context", ["returns", "user_feedback"])
@pytest.mark.parametrize("report_mode", [False, True])
def test_overview_keeps_weighted_totals_and_report_primary_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    analysis_context: str,
    report_mode: bool,
) -> None:
    context, version, service = _ready_result(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET snapshot_json = ? WHERE id = 'task-1'",
            ('{"analysis_context":"' + analysis_context + '"}',),
        )
    _, dashboard = _create_dashboard(service, str(version["version_id"]))
    observed = []
    original = dashboard_insight_overview._collect_semantic_breakdown

    def capture_weighted_scope(scope, total):
        observed.append((scope.records_table, scope.where_sql, scope.params, total))
        return original(scope, total)

    monkeypatch.setattr(
        dashboard_insight_overview,
        "_collect_semantic_breakdown",
        capture_weighted_scope,
    )
    payload = service.insights(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        report_mode=report_mode,
        part="overview",
    )
    total = payload["total_record_count"]
    assert observed == [("dashboard_insight_weighted_units", "1=1", [], total)]
    assert total == 2
    assert sum(item["record_count"] for item in payload["reasons"]) == 2
    assert payload["product_reason_matrix"][0]["total_record_count"] == 2
    for reason in payload["reasons"]:
        assert reason["primary_record_count"] == (None if report_mode else 2)
        assert reason["companion_only_count"] == (None if report_mode else 0)
        assert reason["primary_rate"] == (None if report_mode else 100.0)
    assert (payload["selected_reason"] is None) == report_mode


@pytest.mark.parametrize("subject", [None, "PRODUCT", "UNKNOWN"])
def test_overview_empty_product_scope_keeps_option_date_range(tmp_path: Path, subject):
    _, version, service = _ready_result(tmp_path)
    _, dashboard = _create_dashboard(service, str(version["version_id"]))
    arguments = (str(dashboard["id"]), str(dashboard["version"]["version_id"]))
    baseline = service.insights(*arguments, subject=subject, part="overview")
    empty = service.insights(
        *arguments, subject=subject, product_name="未出现的合成商品", part="overview"
    )
    assert empty["date_range"] == baseline["date_range"]
    assert empty["total_record_count"] == 0
    assert empty["selected_reason"] is None
    assert empty["reasons"] == empty["product_reason_matrix"] == []
