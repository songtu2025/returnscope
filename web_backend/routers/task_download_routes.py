from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from web_backend.task_service import (
    TaskService,
)


def _reject_current_download(segments: list[dict[str, Any]]) -> None:
    if any(segment.get("result_version_id") for segment in segments):
        raise HTTPException(
            status_code=410,
            detail="同步下载已停用，请在分类结果页点击下载，后台生成文件。",
        )


def register_task_download_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get(
        "/api/tasks/{task_id}/download",
        responses={410: {"description": "请使用后台导出"}},
    )
    def download_result(task_id: str, _user: User) -> Response:
        task = task_service.get(task_id)
        _reject_current_download(task.get("segments", []) if task else [])
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

    @router.get(
        "/api/tasks/{task_id}/segments/{segment_key:path}/download",
        responses={410: {"description": "请使用后台导出"}},
    )
    def download_segment_result(
        task_id: str,
        segment_key: str,
        _user: User,
    ) -> Response:
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
        _reject_current_download([segment] if segment else [])
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
