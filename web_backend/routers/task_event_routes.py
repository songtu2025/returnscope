import asyncio
import json
from typing import Annotated, Any, AsyncIterator, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from web_backend.task_service import (
    TaskService,
)


def register_task_event_routes(
    router: APIRouter,
    task_service: TaskService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

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
