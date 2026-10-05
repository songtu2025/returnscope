from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends

from web_backend.api_contracts.tasks import (
    TaskParallelismRequest,
    TaskSegmentActionRequest,
    TaskSegmentOrderRequest,
    TaskSegmentRetryRequest,
)
from web_backend.classification_result_service import ResultPublicationError
from web_backend.routers.task_route_support import task_request_errors
from web_backend.task_service import (
    TaskResultPublishConflict,
    TaskRevisionConflict,
    TaskService,
)


def register_segment_retry_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/tasks/{task_id}/segments/{segment_key:path}/retry")
    def retry_task_segment(
        task_id: str,
        segment_key: str,
        payload: TaskSegmentRetryRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.retry_segment(
                task_id=task_id,
                segment_key=segment_key,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )

    @router.post("/api/tasks/{task_id}/segments/{segment_id}/retry-result-publish")
    def retry_segment_result_publish(
        task_id: str,
        segment_id: str,
        payload: TaskSegmentRetryRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(
            ResultPublicationError, TaskResultPublishConflict, TaskRevisionConflict
        ):
            return task_service.retry_result_publish(
                task_id=task_id,
                segment_id=segment_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )


def register_segment_control_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.put("/api/tasks/{task_id}/segments/order")
    def reorder_task_segments(
        task_id: str,
        payload: TaskSegmentOrderRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.reorder_segments(
                task_id=task_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )

    @router.patch("/api/tasks/{task_id}/parallelism")
    def update_task_parallelism(
        task_id: str,
        payload: TaskParallelismRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.set_parallelism(
                task_id=task_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )

    @router.post("/api/tasks/{task_id}/segments/{segment_key:path}/{action}")
    def control_task_segment(
        task_id: str,
        segment_key: str,
        action: str,
        payload: TaskSegmentActionRequest,
        user: User,
    ) -> dict[str, Any]:
        with task_request_errors(TaskRevisionConflict):
            return task_service.segment_action(
                task_id=task_id,
                segment_key=segment_key,
                action=action,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
