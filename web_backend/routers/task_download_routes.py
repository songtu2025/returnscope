from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from web_backend.task_service import (
    TaskService,
)


def register_task_download_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/tasks/{task_id}/download")
    def download_result(task_id: str, _user: User) -> FileResponse:
        task = task_service.get(task_id)
        if task is None or not task.get("result_file_path"):
            raise HTTPException(status_code=404, detail="结果文件尚未生成")
        path = Path(str(task["result_file_path"]))
        if not path.exists():
            raise HTTPException(status_code=404, detail="结果文件不存在")
        return FileResponse(
            path,
            filename=f"{task_id}-analysis-v{task['result_version']}.xlsx",
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    @router.get("/api/tasks/{task_id}/segments/{segment_key:path}/download")
    def download_segment_result(
        task_id: str,
        segment_key: str,
        _user: User,
    ) -> FileResponse:
        task = task_service.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        segment = next(
            (
                value
                for value in task.get("segments", [])
                if value["segment_key"] == segment_key
            ),
            None,
        )
        if segment is None or not segment.get("result_file_path"):
            raise HTTPException(status_code=404, detail="Listing 结果尚未生成")
        path = Path(str(segment["result_file_path"]))
        if not path.exists():
            raise HTTPException(status_code=404, detail="Listing 结果不存在")
        return FileResponse(
            path,
            filename=f"{task_id}-{segment_key}-analysis.xlsx",
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
