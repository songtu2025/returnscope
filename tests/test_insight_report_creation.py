from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from test_insight_reports import _service_context

from web_backend.database import Database
from web_backend.insight_report_service import PROMPT_VERSION, InsightReportConflict


def _creation_state(
    database: Database,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with database.connect() as connection:
        reports = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM ai_insight_reports ORDER BY id"
            )
        ]
        audits = [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM audit_logs
                WHERE entity_type = 'ai_insight_report' ORDER BY id
                """
            )
        ]
    return reports, audits


@pytest.mark.parametrize("entrypoint", ("dashboard", "results"))
@pytest.mark.parametrize("effort", ("medium", "high"))
def test_creation_maps_target_model_and_audit_fields(
    tmp_path: Path, entrypoint: str, effort: str
) -> None:
    context, dashboard, service, _captured = _service_context(tmp_path)
    if entrypoint == "results":
        sources = service.dashboard_service.sources(
            str(dashboard["id"]), str(dashboard["version"]["version_id"])
        )
        result_ids = [str(source["result_version_id"]) for source in sources]
        plan = service.dashboard_service.preflight(result_ids, {})
        created = service.create_from_results(
            result_version_ids=result_ids,
            filters={},
            plan_hash=plan["plan_hash"],
            model_id="model-1",
            reasoning_effort=effort,
            actor_id="user-1",
        )
        dashboard, report = created["dashboard"], created["report"]
    else:
        report = service.create_for_dashboard(
            str(dashboard["id"]),
            str(dashboard["version"]["version_id"]),
            model_id="model-1",
            reasoning_effort=effort,
            actor_id="user-1",
        )

    assert report["dashboard_id"] == dashboard["id"]
    assert report["dashboard_version_id"] == dashboard["version"]["version_id"]
    assert report["model_id"] == "model-1"
    assert report["model_key"] == "model-primary"
    assert report["config_version_id"] == "config-1"
    assert report["reasoning_effort"] == effort
    assert report["parent_job_id"] is None
    assert report["created_by"] == "user-1"
    assert report["prompt_version"] == PROMPT_VERSION
    assert report["status"] == report["stage"] == "queued"
    assert report["attempt_no"] == 1
    assert report["version_no"] is None
    reports, audits = _creation_state(context.database)
    assert len(reports) == len(audits) == 1
    assert reports[0]["id"] == audits[0]["entity_id"] == report["id"]
    assert audits[0]["action"] == "create"
    assert audits[0]["actor_id"] == report["created_by"]
    assert audits[0]["created_at"] == report["created_at"]
    assert json.loads(audits[0]["after_json"]) == {
        "dashboard_id": dashboard["id"],
        "dashboard_version_id": dashboard["version"]["version_id"],
        "attempt_no": 1,
        "model_id": "model-1",
        "reasoning_effort": effort,
        "parent_job_id": None,
    }


@pytest.mark.parametrize("status", ("queued", "running"))
def test_active_report_rejects_duplicate_without_changing_rows(
    tmp_path: Path, status: str
) -> None:
    context, dashboard, service, _captured = _service_context(tmp_path)
    report = service.create_for_dashboard(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="medium",
        actor_id="user-1",
    )
    if status == "running":
        assert service.claim_next() == report["id"]
    before = _creation_state(context.database)

    with pytest.raises(InsightReportConflict, match="当前数据版本已有报告正在生成"):
        service.create_for_dashboard(
            str(dashboard["id"]),
            str(dashboard["version"]["version_id"]),
            model_id="model-1",
            reasoning_effort="high",
            actor_id="user-1",
        )

    assert _creation_state(context.database) == before


@pytest.mark.parametrize("changed_scope", ("dashboard", "version"))
def test_other_dashboard_or_version_can_create_an_independent_report(
    tmp_path: Path, changed_scope: str
) -> None:
    context, dashboard, service, _captured = _service_context(tmp_path)
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])
    first = service.create_for_dashboard(
        dashboard_id,
        version_id,
        model_id="model-1",
        reasoning_effort="medium",
        actor_id="user-1",
    )
    sources = service.dashboard_service.sources(dashboard_id, version_id)
    result_ids = [str(source["result_version_id"]) for source in sources]
    plan = service.dashboard_service.preflight(result_ids, {})
    if changed_scope == "version":
        other = service.dashboard_service.create_version(
            dashboard_id,
            expected_revision=int(dashboard["revision"]),
            result_version_ids=result_ids,
            filters={},
            plan_hash=plan["plan_hash"],
            reason="合成版本隔离验证",
            actor_id="user-1",
        )
    else:
        other = service.dashboard_service.create(
            name="另一个合成看板",
            description="目标隔离验证",
            result_version_ids=result_ids,
            filters={},
            plan_hash=plan["plan_hash"],
            reason="合成看板隔离验证",
            actor_id="user-1",
        )

    second = service.create_for_dashboard(
        str(other["id"]),
        str(other["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )

    assert second["id"] != first["id"]
    assert second["dashboard_id"] == other["id"]
    assert second["dashboard_version_id"] == other["version"]["version_id"]
    assert second["dashboard_version_id"] != version_id
    assert second["attempt_no"] == (2 if changed_scope == "version" else 1)
    assert second["version_no"] is None
    assert service.get(str(first["id"])) == {
        **first,
        "source_outdated": int(changed_scope == "version"),
    }
    reports, audits = _creation_state(context.database)
    assert len(reports) == len(audits) == 2


def test_retry_preserves_failed_job_snapshot_after_catalog_changes(
    tmp_path: Path,
) -> None:
    context, dashboard, service, _captured = _service_context(
        tmp_path, client_error="合成模型失败"
    )
    queued = service.create_for_dashboard(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="medium",
        actor_id="user-1",
    )
    assert service.claim_next() == queued["id"]
    service.run(str(queued["id"]))
    failed = service.get(str(queued["id"]))
    assert failed["status"] == "failed"
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE api_models SET model_key = 'changed-model',
                supported_efforts_json = '["low"]', active = 0,
                validation_status = 'failed'
            WHERE id = 'model-1'
            """
        )
        connection.execute(
            "UPDATE api_connections SET active_version_id = NULL WHERE id = 'connection-1'"
        )

    retried = service.retry(str(failed["id"]), "user-1")

    for field in (
        "dashboard_id",
        "dashboard_version_id",
        "model_id",
        "model_key",
        "config_version_id",
        "reasoning_effort",
    ):
        assert retried[field] == failed[field]
    assert retried["id"] != failed["id"]
    assert retried["parent_job_id"] == failed["id"]
    assert retried["created_by"] == "user-1"
    assert retried["attempt_no"] == 2
    assert retried["version_no"] is None
    assert service.get(str(failed["id"])) == failed
    _reports, audits = _creation_state(context.database)
    created = next(audit for audit in audits if audit["entity_id"] == retried["id"])
    assert created["action"] == "create"
    assert json.loads(created["after_json"])["parent_job_id"] == failed["id"]
    retry = next(audit for audit in audits if audit["action"] == "retry")
    assert retry["entity_id"] == failed["id"]
    assert json.loads(retry["after_json"]) == {"new_job_id": retried["id"]}
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM ai_insight_report_versions"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("entrypoint", ("dashboard", "retry"))
@pytest.mark.parametrize(
    "trigger_sql",
    (
        """
        CREATE TRIGGER fail_report_insert BEFORE INSERT ON ai_insight_reports
        BEGIN SELECT RAISE(ABORT, 'synthetic report failure'); END
        """,
        """
        CREATE TRIGGER fail_create_audit BEFORE INSERT ON audit_logs
        WHEN NEW.entity_type = 'ai_insight_report' AND NEW.action = 'create'
        BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END
        """,
    ),
)
def test_report_and_creation_audit_roll_back_together(
    tmp_path: Path, entrypoint: str, trigger_sql: str
) -> None:
    context, dashboard, service, _captured = _service_context(
        tmp_path, client_error="合成模型失败"
    )
    report = service.create_for_dashboard(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="medium",
        actor_id="user-1",
    )
    assert service.claim_next() == report["id"]
    service.run(str(report["id"]))
    assert service.get(str(report["id"]))["status"] == "failed"
    before = _creation_state(context.database)
    with context.database.transaction() as connection:
        connection.execute(trigger_sql)

    with pytest.raises(sqlite3.IntegrityError, match="synthetic .* failure"):
        if entrypoint == "retry":
            service.retry(str(report["id"]), "user-1")
        else:
            service.create_for_dashboard(
                str(dashboard["id"]),
                str(dashboard["version"]["version_id"]),
                model_id="model-1",
                reasoning_effort="high",
                actor_id="user-1",
            )

    assert _creation_state(context.database) == before
