from pathlib import Path

import pytest
from test_classification_result_pool import _publish, _seed_result_context
from test_insight_reports import _service_context

from web_backend.common import json_text
from web_backend.operations_service import WorkbenchService


def _insert_paused_task(database) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, listing, status, stage,
                snapshot_json, created_at, heartbeat_at
            ) VALUES ('task-paused', '暂停任务', 'user-1', 'version-returns',
                      'version-products', 'config-1', 'SEEKWAY:US', 'L2',
                      'paused', '语义分析', '{}', ?, ?)
            """,
            ("2026-08-12T03:00:00+00:00", "2026-08-12T03:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                taxonomy_version, scope_json, status, created_at, heartbeat_at
            ) VALUES ('segment-paused', 'task-paused', 'L2', 'footwear',
                      '鞋履智能体', 'taxonomy-v1', ?, 'paused', ?, ?)
            """,
            (
                json_text({"store": "SEEKWAY:US", "listing": "L2"}),
                "2026-08-12T03:00:00+00:00",
                "2026-08-12T03:00:00+00:00",
            ),
        )


def test_workbench_actions_are_fact_based_and_priority_sorted(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    _insert_paused_task(context.database)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE tasks SET status = 'blocked', message = '缺少品类',
                             heartbeat_at = '2026-08-12T01:00:00+00:00'
            WHERE id = 'task-1'
            """
        )
        connection.execute(
            """
            UPDATE task_segments SET status = 'failed', error = '调用失败',
                   heartbeat_at = '2026-08-12T02:00:00+00:00'
            WHERE id = 'segment-1'
            """
        )
        connection.execute(
            """
            UPDATE classification_result_versions
            SET quality_status = 'review_required',
                published_at = '2026-08-12T04:00:00+00:00'
            WHERE id = ?
            """,
            (version["version_id"],),
        )

    summary = WorkbenchService(context.database).summary(limit=10)
    assert [item["type"] for item in summary["actions"]] == [
        "blocked",
        "failed",
        "review_required",
        "paused",
        "paused",
    ]
    blocked = summary["actions"][0]
    assert blocked["object_id"] == "task-1"
    assert blocked["target"] == {"route": "tasks", "task_id": "task-1"}
    review = summary["actions"][2]
    assert review["result_version_id"] == version["version_id"]
    assert review["target"]["action"] == "review"
    assert summary["counts"]["blocked_tasks"] == 1
    assert summary["counts"]["failed_segments"] == 1
    assert summary["counts"]["review_required_results"] == 1
    assert summary["counts"]["paused_segments"] == 1


@pytest.mark.parametrize(
    "stage,reason",
    [
        ("queued", "等待生成"),
        ("preparing_evidence", "正在准备证据"),
        ("calling_model", "模型正在解释证据"),
        ("assembling_report", "正在装配报告"),
        ("publishing", "正在发布报告"),
        ("unknown", "正在生成报告"),
    ],
)
def test_workbench_report_actions_keep_generation_stage_and_navigation(
    tmp_path: Path, stage: str, reason: str
) -> None:
    context, dashboard, reports, _ = _service_context(tmp_path)
    report = reports.create_for_dashboard(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE ai_insight_reports SET stage=?, status=? WHERE id=?",
            (stage, "queued" if stage == "queued" else "running", report["id"]),
        )
    summary = WorkbenchService(context.database).summary(limit=20)
    action = next(
        item for item in summary["actions"] if item["object_id"] == report["id"]
    )
    assert action["type"] == "report_running"
    assert action["reason"] == reason
    assert action["actor"] == {"id": "user-1", "name": "用户一"}
    assert action["target"] == {
        "route": "analysis-dashboards",
        "dashboard_id": dashboard["id"],
        "version_id": dashboard["version"]["version_id"],
        "report_id": report["id"],
        "tab": "report",
    }
    assert summary["counts"]["running_reports"] == 1
