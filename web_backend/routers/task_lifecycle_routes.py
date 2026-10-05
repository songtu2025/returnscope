from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.api_contracts.tasks import (
    TaskActionRequest,
    TaskRenameRequest,
    TaskSegmentActionRequest,
)
from web_backend.routers.task_route_support import task_request_errors
from web_backend.task_service import (
    TaskRevisionConflict,
    TaskService,
)


def register_task_detail_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/tasks/{task_id}")
    def get_task(task_id: str, _user: User) -> dict[str, Any]:
        task = task_service.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task

    @router.patch("/api/tasks/{task_id}")
    def rename_task(
        task_id: str,
        payload: TaskRenameRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.rename(
                task_id=task_id,
                title=payload.title,
                note=payload.note,
                expected_revision=payload.expected_revision,
                actor_id=str(user["id"]),
            )


def register_task_stop_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/tasks/{task_id}/cancel")
    def cancel_task(
        task_id: str,
        payload: TaskActionRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.cancel(
                task_id,
                str(user["id"]),
                payload.note,
                payload.expected_revision,
            )

    @router.post("/api/tasks/{task_id}/pause")
    def pause_task(
        task_id: str,
        payload: TaskSegmentActionRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.pause(
                task_id=task_id,
                actor_id=str(user["id"]),
                expected_revision=payload.expected_revision,
            )


def register_task_restart_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/tasks/{task_id}/retry", status_code=201)
    def retry_task(task_id: str, user: User) -> dict[str, Any]:
        with task_request_errors():
            return task_service.retry(task_id, str(user["id"]))

    @router.post("/api/tasks/{task_id}/resume")
    def resume_task(
        task_id: str,
        payload: TaskActionRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.resume(
                task_id=task_id,
                actor_id=str(user["id"]),
                expected_revision=payload.expected_revision,
                note=payload.note,
            )
