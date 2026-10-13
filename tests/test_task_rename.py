import pytest
from test_task_planning import _create_task, _database_with_inputs

from web_backend.api_contracts.tasks import TaskRenameRequest
from web_backend.task_service import TaskRevisionConflict, TaskService


def test_rename_uses_list_revision_and_allows_duplicate_names(tmp_path):
    database, _, _ = _database_with_inputs(tmp_path)
    first = _create_task(database, "run_ready")
    second = _create_task(database, "run_ready")
    service = TaskService(database)
    rows = {item["id"]: item for item in service.list()}
    for task in (first, second):
        item = rows[task["id"]]
        payload = TaskRenameRequest(
            title="同名任务", expected_revision=item["revision"]
        )
        assert payload.note == ""
        updated = service.rename(
            task_id=item["id"],
            title=payload.title,
            note=payload.note,
            expected_revision=payload.expected_revision,
            actor_id=task["owner_id"],
        )
        assert updated["title"] == "同名任务"
        assert updated["revision"] == item["revision"] + 1
        assert updated["status"] == task["status"]
    assert first["id"] != second["id"]
    renamed = {item["id"]: item for item in service.list()}
    assert renamed[first["id"]]["title"] == renamed[second["id"]]["title"]
    with pytest.raises(TaskRevisionConflict):
        service.rename(
            first["id"], "再次修改", "", first["revision"], first["owner_id"]
        )
    with database.connect() as connection:
        audits = connection.execute(
            "SELECT actor_id, before_json, after_json FROM audit_logs WHERE action = 'rename'"
        ).fetchall()
    assert len(audits) == 2
    assert all(row["actor_id"] == first["owner_id"] for row in audits)


def test_rename_rejects_blank_name(tmp_path):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    with pytest.raises(ValueError, match="任务名称不能为空"):
        TaskService(database).rename(
            task["id"], "  ", "", task["revision"], task["owner_id"]
        )
