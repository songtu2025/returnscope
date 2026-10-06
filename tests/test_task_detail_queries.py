import pytest
from test_task_planning import _create_task, _database_with_inputs

from web_backend.task_service import TaskService


def _add_segment(database, source_id, key, status):
    with database.transaction() as connection:
        item = dict(
            connection.execute(
                "SELECT * FROM task_segments WHERE id = ?", (source_id,)
            ).fetchone()
        )
        item.update(id=key, segment_key=key, status=status, execution_order=20)
        columns = ",".join(item)
        values = ",".join("?" for _ in item)
        connection.execute(
            f"INSERT INTO task_segments({columns}) VALUES ({values})",
            tuple(item.values()),
        )


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"pause": 1, "running": 3, "parallel": 1}, "批量任务已暂停"),
        ({"running": 1, "parallel": 1}, "本批量并发已满：1/1"),
        ({"running": 3}, "本批量并发已满：3/3"),
        ({"external": 3}, "个人运行槽位已满：3/3"),
        ({}, "我的队列第 1 位"),
        ({"status": "retry_pending"}, "我的队列第 1 位"),
        ({"status": "paused", "failures": 2, "error": "异常"}, "已由用户暂停"),
        (
            {"status": "paused", "failures": 3, "error": "异常"},
            "模型服务异常，任务已暂停",
        ),
        ({"status": "paused", "failures": 4}, "已由用户暂停"),
        ({"status": "completed"}, None),
    ],
)
def test_detail_wait_reason_and_capacity_priority(tmp_path, changes, expected):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    segment = next(x for x in task["segments"] if x["status"] == "queued")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET pause_requested = ?, max_parallel_segments = ? WHERE id = ?",
            (changes.get("pause", 0), changes.get("parallel", 3), task["id"]),
        )
        connection.execute(
            "UPDATE task_segments SET status = ?, model_failures = ?, error = ? WHERE id = ?",
            (
                changes.get("status", "queued"),
                changes.get("failures", 0),
                changes.get("error"),
                segment["id"],
            ),
        )
    for index in range(changes.get("running", 0)):
        _add_segment(database, segment["id"], f"own-{index}", "running")
    if changes.get("external"):
        other = _create_task(database, "run_ready")
        source = next(x for x in other["segments"] if x["status"] == "queued")
        for index in range(changes["external"]):
            _add_segment(database, source["id"], f"other-{index}", "running")
    result = TaskService(database).get(str(task["id"]))
    actual = next(x for x in result["segments"] if x["id"] == segment["id"])
    assert actual.get("wait_reason") == expected
    assert result["running_segments"] == changes.get("running", 0)
    assert result["owner_running_segments"] == changes.get("running", 0) + changes.get(
        "external", 0
    )


@pytest.mark.parametrize("missing, expected", [(False, 5), (True, 2)])
def test_detail_uses_one_connection_and_preserves_query_budget(
    tmp_path, monkeypatch, missing, expected
):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    connect = database.connect
    queries = []
    openings = []

    def traced_connect():
        openings.append(True)
        connection = connect()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(database, "connect", traced_connect)
    result = service.get("missing" if missing else str(task["id"]))
    assert len(openings) == 1
    assert (
        len([sql for sql in queries if sql.lstrip().startswith("SELECT")]) == expected
    )
    assert (result is None) == missing
