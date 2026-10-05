from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, Query

from web_backend.api_contracts.tasks import (
    TaskArchiveRequest,
    TaskCreateRequest,
    TaskPreflightRequest,
    TaskReplanPreflightRequest,
    TaskReplanRequest,
)
from web_backend.routers.task_route_support import task_request_errors
from web_backend.task_service import (
    TaskPlanConflict,
    TaskRevisionConflict,
    TaskService,
)


def register_task_collection_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/tasks")
    def list_tasks(
        _user: User,
        status: str | None = Query(default=None),
        owner_id: str | None = Query(default=None),
        include_archived: bool = Query(default=False),
    ) -> list[dict[str, Any]]:
        return task_service.list(
            status=status,
            owner_id=owner_id,
            include_archived=include_archived,
        )

    @router.post("/api/tasks/preflight")
    def preflight_task(
        payload: TaskPreflightRequest,
        _user: User,
    ) -> dict[str, Any]:
        with task_request_errors():
            return task_service.preflight(**payload.model_dump())

    @router.post("/api/tasks", status_code=201)
    def create_task(payload: TaskCreateRequest, user: User) -> dict[str, Any]:
        with task_request_errors(TaskPlanConflict):
            return task_service.create(actor_id=str(user["id"]), **payload.model_dump())

    @router.post("/api/tasks/archive")
    def archive_tasks(
        payload: TaskArchiveRequest,
        user: User,
    ) -> list[dict[str, Any]]:
        with task_request_errors():
            return task_service.set_archived(
                task_ids=payload.task_ids,
                archived=payload.archived,
                actor_id=str(user["id"]),
            )


def register_task_replan_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/tasks/{task_id}/replan/preflight")
    def preflight_replan(
        task_id: str,
        payload: TaskReplanPreflightRequest,
        _user: User,
    ) -> dict[str, Any]:
        with task_request_errors():
            return task_service.replan_preflight(
                task_id,
                payload.product_version_id,
            )

    @router.post("/api/tasks/{task_id}/replan")
    def replan_task(
        task_id: str,
        payload: TaskReplanRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskPlanConflict, TaskRevisionConflict):
            return task_service.replan(
                task_id=task_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
