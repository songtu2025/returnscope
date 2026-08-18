import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse

from web_backend.analysis_service import AnalysisFilters, AnalysisService
from web_backend.api_schemas import (
    TaskActionRequest,
    TaskCreateRequest,
    TaskParallelismRequest,
    TaskPreflightRequest,
    TaskRenameRequest,
    TaskReplanPreflightRequest,
    TaskReplanRequest,
    TaskSegmentActionRequest,
    TaskSegmentOrderRequest,
    TaskSegmentRetryRequest,
)
from web_backend.classification_result_service import ResultPublicationError
from web_backend.task_service import (
    TaskPlanConflict,
    TaskResultPublishConflict,
    TaskRevisionConflict,
    TaskService,
)


def analysis_filters(
    start_date: date | None = None,
    end_date: date | None = None,
    category_a: str | None = None,
    category_b: str | None = None,
    listing: str | None = None,
    sku: str | None = None,
    asin: str | None = None,
    reason: str | None = None,
    status: str | None = None,
    problem_code: str | None = None,
    claim_relation: str | None = None,
    dimension: str = "listing",
    focus_problem: str | None = None,
    page: int = 1,
    page_size: int = 50,
    view: str = "all",
) -> AnalysisFilters:
    return AnalysisFilters(
        start_date=start_date,
        end_date=end_date,
        category_a=category_a,
        category_b=category_b,
        listing=listing,
        sku=sku,
        asin=asin,
        reason=reason,
        status=status,
        problem_code=problem_code,
        claim_relation=claim_relation,
        dimension=dimension,
        focus_problem=focus_problem,
        page=page,
        page_size=page_size,
        view=view,
    )


def create_task_router(
    task_service: TaskService,
    analysis_service: AnalysisService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/tasks")
    def list_tasks(
        _user: User,
        status: str | None = Query(default=None),
        owner_id: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        return task_service.list(status=status, owner_id=owner_id)

    @router.post("/api/tasks/preflight")
    def preflight_task(
        payload: TaskPreflightRequest,
        _user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.preflight(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks", status_code=201)
    def create_task(payload: TaskCreateRequest, user: User) -> dict[str, Any]:
        try:
            return task_service.create(actor_id=str(user["id"]), **payload.model_dump())
        except TaskPlanConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/replan/preflight")
    def preflight_replan(
        task_id: str,
        payload: TaskReplanPreflightRequest,
        _user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.replan_preflight(
                task_id,
                payload.product_version_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/replan")
    def replan_task(
        task_id: str,
        payload: TaskReplanRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.replan(
                task_id=task_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except (TaskPlanConflict, TaskRevisionConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/segments/{segment_key:path}/retry")
    def retry_task_segment(
        task_id: str,
        segment_key: str,
        payload: TaskSegmentRetryRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.retry_segment(
                task_id=task_id,
                segment_key=segment_key,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post(
        "/api/tasks/{task_id}/segments/{segment_id}/retry-result-publish"
    )
    def retry_segment_result_publish(
        task_id: str,
        segment_id: str,
        payload: TaskSegmentRetryRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.retry_result_publish(
                task_id=task_id,
                segment_id=segment_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except (
            ResultPublicationError,
            TaskResultPublishConflict,
            TaskRevisionConflict,
        ) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/api/tasks/{task_id}/segments/order")
    def reorder_task_segments(
        task_id: str,
        payload: TaskSegmentOrderRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.reorder_segments(
                task_id=task_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/api/tasks/{task_id}/parallelism")
    def update_task_parallelism(
        task_id: str,
        payload: TaskParallelismRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.set_parallelism(
                task_id=task_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/segments/{segment_key:path}/{action}")
    def control_task_segment(
        task_id: str,
        segment_key: str,
        action: str,
        payload: TaskSegmentActionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.segment_action(
                task_id=task_id,
                segment_key=segment_key,
                action=action,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/tasks/{task_id}/analysis")
    def get_task_analysis(
        task_id: str,
        _user: User,
        filters: Annotated[AnalysisFilters, Depends(analysis_filters)],
    ) -> dict[str, Any]:
        try:
            return analysis_service.get(task_id, filters)
        except ValueError as exc:
            status_code = 404 if str(exc) == "任务不存在" else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @router.get("/api/tasks/{task_id}/analysis/download")
    def download_filtered_analysis(
        task_id: str,
        _user: User,
        filters: Annotated[AnalysisFilters, Depends(analysis_filters)],
    ) -> Response:
        try:
            content, filename = analysis_service.export_filtered(task_id, filters)
        except ValueError as exc:
            status_code = 404 if str(exc) == "任务不存在" else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

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
        try:
            return task_service.rename(
                task_id=task_id,
                title=payload.title,
                note=payload.note,
                expected_revision=payload.expected_revision,
                actor_id=str(user["id"]),
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/cancel")
    def cancel_task(
        task_id: str,
        payload: TaskActionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.cancel(
                task_id,
                str(user["id"]),
                payload.note,
                payload.expected_revision,
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/pause")
    def pause_task(
        task_id: str,
        payload: TaskSegmentActionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.pause(
                task_id=task_id,
                actor_id=str(user["id"]),
                expected_revision=payload.expected_revision,
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/retry", status_code=201)
    def retry_task(task_id: str, user: User) -> dict[str, Any]:
        try:
            return task_service.retry(task_id, str(user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/tasks/{task_id}/resume")
    def resume_task(
        task_id: str,
        payload: TaskActionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return task_service.resume(
                task_id=task_id,
                actor_id=str(user["id"]),
                expected_revision=payload.expected_revision,
                note=payload.note,
            )
        except TaskRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/tasks/{task_id}/events")
    async def stream_task_events(
        task_id: str,
        _user: User,
        after: int = Query(default=0, ge=0),
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if task_service.get(task_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")

        async def event_stream() -> AsyncIterator[str]:
            try:
                resumed_after = int(last_event_id or 0)
            except ValueError:
                resumed_after = 0
            last_id = max(after, resumed_after)
            for _ in range(60):
                events = task_service.events(task_id, last_id)
                for event in events:
                    last_id = int(event["id"])
                    yield (
                        f"id: {last_id}\n"
                        f"event: task\n"
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    )
                task = task_service.get(task_id)
                if task and task["status"] in {
                    "completed",
                    "failed",
                    "cancelled",
                    "blocked",
                    "partial",
                }:
                    yield "event: close\ndata: {}\n\n"
                    return
                yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

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

    return router
