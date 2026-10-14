import json
import logging
import sqlite3
from unittest.mock import Mock

import pytest
from test_agent_runner_segment_outcomes import _latest_run
from test_agent_runner_segment_outcomes import runtime as runtime

from web_backend.agent_runner import AgentRunner
from web_backend.classification_result_service import ResultPublicationError
from web_backend.task_execution.failure_diagnostics import log_segment_failure


def test_diagnostic_keeps_database_code_and_origin_without_error_payload(caplog):
    with pytest.raises(ResultPublicationError) as caught:
        try:
            with sqlite3.connect(":memory:") as connection:
                connection.execute("SELECT * FROM synthetic_private_payload")
        except sqlite3.Error as error:
            raise ResultPublicationError("synthetic-private-secret") from error
    with caplog.at_level(logging.ERROR):
        log_segment_failure("task-1", "segment-1", "result_publish", caught.value)
    assert "synthetic-private-secret" not in caplog.text
    assert "synthetic_private_payload" not in caplog.text
    assert "SELECT" not in caplog.text
    details = json.loads(caplog.records[-1].getMessage().split("segment_failure ")[1])
    assert details["sqlite_code"] == sqlite3.SQLITE_ERROR
    assert details["phase"] == "result_publish"
    assert details["root_error_type"] == "OperationalError"
    assert details["source"].startswith("test_task_failure_diagnostics.py:")


def test_corrupt_checkpoint_finishes_as_failed_without_losing_progress(runtime, caplog):
    runner, seed = runtime.runner, runtime.seed
    checkpoint = runtime.context.checkpoint_path
    checkpoint.write_text("{invalid", encoding="utf-8")
    with seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_json_path=?, progress_current=2, progress_total=5 WHERE id=?",
            (str(checkpoint), seed.segment_id),
        )
    runner._segment_run_context = AgentRunner._segment_run_context.__get__(runner)
    runner._execute_segment = Mock()
    with caplog.at_level(logging.ERROR):
        runner.run_segment(seed.task_id, seed.segment_id)
    segment = runner._load_segment(seed.segment_id)
    assert segment["status"] == "failed"
    assert segment["progress_current"] == 2
    assert segment["result_json_path"] == str(checkpoint)
    assert checkpoint.read_text() == "{invalid"
    runner._execute_segment.assert_not_called()
    details = json.loads(
        next(
            record.getMessage().split("segment_failure ")[1]
            for record in caplog.records
            if record.getMessage().startswith("segment_failure ")
        )
    )
    assert details["phase"] == "checkpoint_load"
    assert details["root_error_type"] == "JSONDecodeError"


def test_checkpoint_save_error_is_diagnosed_before_failure_recovery(runtime, caplog):
    runner = runtime.runner
    runner._write_checkpoint = Mock(
        side_effect=PermissionError("synthetic-private-path")
    )
    runner._finish_failed_segment = Mock()
    runner._execute_segment = Mock(
        side_effect=lambda context: runner._save_segment_checkpoint(
            context, _latest_run(runtime.seed.results)
        )
    )
    with caplog.at_level(logging.ERROR):
        runner.run_segment(runtime.seed.task_id, runtime.seed.segment_id)
    assert runtime.context.phase == "checkpoint_save"
    runner._finish_failed_segment.assert_called_once()
    assert "checkpoint_save" in caplog.text
    assert "PermissionError" in caplog.text
    assert "synthetic-private-path" not in caplog.text


@pytest.mark.parametrize(
    "phase", ["data_loading", "configuration", "model_analysis", "runtime_metrics"]
)
def test_runner_reports_failed_phase_without_private_payload(runtime, caplog, phase):
    def fail(context):
        context.phase = phase
        raise RuntimeError("synthetic-private-payload")

    runtime.runner._execute_segment = Mock(side_effect=fail)
    runtime.runner._finish_failed_segment = Mock()
    with caplog.at_level(logging.ERROR):
        runtime.runner.run_segment(runtime.seed.task_id, runtime.seed.segment_id)
    details = json.loads(
        next(
            record.getMessage().split("segment_failure ")[1]
            for record in caplog.records
            if record.getMessage().startswith("segment_failure ")
        )
    )
    assert details["phase"] == phase
    assert "synthetic-private-payload" not in caplog.text
    runtime.runner._finish_failed_segment.assert_called_once()
