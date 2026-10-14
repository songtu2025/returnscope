from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from web_backend.analysis_service import AnalysisService
from web_backend.classification_result_service import ResultPublicationError
from web_backend.routers.tasks import create_task_router
from web_backend.task_service import (
    TaskPlanConflict,
    TaskResultPublishConflict,
    TaskRevisionConflict,
    TaskService,
)

ROUTES = [
    "GET|/api/tasks/recycle|recycled_listings|200",
    "GET|/api/tasks|list_tasks|200",
    "POST|/api/tasks/preflight|preflight_task|200",
    "POST|/api/tasks|create_task|201",
    "POST|/api/tasks/archive|archive_tasks|200",
    "POST|/api/tasks/{task_id}/replan/preflight|preflight_replan|200",
    "POST|/api/tasks/{task_id}/replan|replan_task|200",
    "POST|/api/tasks/{task_id}/segments/{segment_key:path}/retry|retry_task_segment|200",
    "POST|/api/tasks/{task_id}/segments/{segment_id}/retry-result-publish|retry_segment_result_publish|200",
    "PUT|/api/tasks/{task_id}/segments/order|reorder_task_segments|200",
    "PATCH|/api/tasks/{task_id}/parallelism|update_task_parallelism|200",
    "POST|/api/tasks/{task_id}/segments/{segment_key:path}/{action}|control_task_segment|200",
    "GET|/api/tasks/{task_id}/analysis|get_task_analysis|200",
    "GET|/api/tasks/{task_id}/analysis/download|download_filtered_analysis|200",
    "GET|/api/tasks/{task_id}|get_task|200",
    "PATCH|/api/tasks/{task_id}|rename_task|200",
    "POST|/api/tasks/{task_id}/cancel|cancel_task|200",
    "POST|/api/tasks/{task_id}/pause|pause_task|200",
    "POST|/api/tasks/{task_id}/retry|retry_task|201",
    "POST|/api/tasks/{task_id}/resume|resume_task|200",
    "GET|/api/tasks/{task_id}/events|stream_task_events|200",
    "GET|/api/tasks/{task_id}/download|download_result|200",
    "GET|/api/tasks/{task_id}/segments/{segment_key:path}/download|download_segment_result|200",
]


SERVICE_METHODS = {
    "preflight_task": "preflight",
    "create_task": "create",
    "archive_tasks": "set_archived",
    "preflight_replan": "replan_preflight",
    "replan_task": "replan",
    "retry_task_segment": "retry_segment",
    "retry_segment_result_publish": "retry_result_publish",
    "reorder_task_segments": "reorder_segments",
    "update_task_parallelism": "set_parallelism",
    "control_task_segment": "segment_action",
    "rename_task": "rename",
    "cancel_task": "cancel",
    "pause_task": "pause",
    "retry_task": "retry",
    "resume_task": "resume",
}


CONFLICT_CASES = [
    ("create_task", TaskPlanConflict),
    ("replan_task", TaskPlanConflict),
    ("replan_task", TaskRevisionConflict),
    ("retry_task_segment", TaskRevisionConflict),
    ("retry_segment_result_publish", ResultPublicationError),
    ("retry_segment_result_publish", TaskResultPublishConflict),
    ("retry_segment_result_publish", TaskRevisionConflict),
    ("reorder_task_segments", TaskRevisionConflict),
    ("update_task_parallelism", TaskRevisionConflict),
    ("control_task_segment", TaskRevisionConflict),
    ("rename_task", TaskRevisionConflict),
    ("cancel_task", TaskRevisionConflict),
    ("pause_task", TaskRevisionConflict),
    ("resume_task", TaskRevisionConflict),
]


SEGMENT_KEY = "SEEKWAY:US/KP001/footwear"


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[SimpleNamespace]:
    result = tmp_path / "analysis.xlsx"
    result.write_bytes(b"synthetic-result")
    task = Mock(spec=TaskService)
    task.recycle = Mock()
    task.recycle.listings.return_value = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }
    task.list.return_value = [{"id": "task-1", "created_by": "another-user"}]
    for method in SERVICE_METHODS.values():
        getattr(task, method).return_value = {"status": "queued"}
    task.set_archived.return_value = [{"id": "task-1", "archived": True}]
    task.get.return_value = {
        "id": "task-1",
        "created_by": "another-user",
        "status": "completed",
        "result_file_path": str(result),
        "result_version": 3,
        "segments": [{"segment_key": SEGMENT_KEY, "result_file_path": str(result)}],
    }
    task.events.return_value = []
    analysis = Mock(spec=AnalysisService)
    analysis.get.return_value = {"total": 1}
    analysis.export_filtered.return_value = (b"filtered-result", "filtered.xlsx")

    def current_user() -> dict[str, str]:
        return {"id": "user-1", "role": "user"}

    app = FastAPI()
    router = create_task_router(task, analysis, current_user)
    app.include_router(router)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            task=task,
            analysis=analysis,
            app=app,
            current_user=current_user,
            result=result,
            router=router,
        )


def _request(harness: SimpleNamespace, name: str) -> Response:
    contract = next(row for row in ROUTES if row.split("|")[2] == name)
    method, path, _, _ = contract.split("|")
    path = (
        path.replace("{task_id}", "task-1")
        .replace("{segment_id}", "segment-1")
        .replace("{segment_key:path}", SEGMENT_KEY)
        .replace("{action}", "resume")
    )
    # 使用所有请求模型均可接受的合成字段，避免读取真实任务或配置。
    body = {
        "dataset_version_id": "dataset-1",
        "product_version_id": "product-1",
        "expected_revision": 3,
        "title": "合成任务",
        "note": "合成操作",
        "reason": "合成原因",
        "plan_hash": "a" * 64,
        "unresolved_policy": "run_ready",
        "task_ids": ["task-1"],
        "archived": True,
        "segment_keys": [SEGMENT_KEY],
        "max_parallel_segments": 2,
    }
    return harness.client.request(method, path, json=body)
