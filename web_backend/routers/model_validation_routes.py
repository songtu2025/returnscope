import asyncio
import json
from typing import Annotated, Any, AsyncIterator, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from web_backend.config_service import ConfigService


def register_model_validation_routes(
    router: APIRouter,
    config_service: ConfigService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/connections/{connection_id}/active-validation")
    def active_validation(
        connection_id: str,
        _user: User,
    ) -> dict[str, Any] | None:
        return config_service.latest_active_validation_run(connection_id)

    @router.get("/api/validation-runs/{run_id}")
    def get_validation_run(run_id: str, _user: User) -> dict[str, Any]:
        run = config_service.get_validation_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="验证记录不存在")
        return run

    @router.get("/api/validation-runs/{run_id}/events")
    async def stream_validation_events(
        run_id: str,
        _user: User,
        after: int = Query(default=0, ge=0),
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if config_service.get_validation_run(run_id) is None:
            raise HTTPException(status_code=404, detail="验证记录不存在")

        return StreamingResponse(
            _validation_event_stream(config_service, run_id, after, last_event_id),
            media_type="text/event-stream",
        )


async def _validation_event_stream(
    config_service: ConfigService,
    run_id: str,
    after: int,
    last_event_id: str | None,
) -> AsyncIterator[str]:
    try:
        resumed_after = int(last_event_id or 0)
    except ValueError:
        resumed_after = 0
    last_id = max(after, resumed_after)
    for _ in range(900):
        events = config_service.validation_events(run_id, last_id)
        for event in events:
            last_id = int(event["id"])
            yield (
                f"id: {last_id}\n"
                f"event: validation\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )
        run = config_service.get_validation_run(run_id)
        if run and run["status"] in {"passed", "failed"}:
            yield "event: close\ndata: {}\n\n"
            return
        yield ": keepalive\n\n"
        await asyncio.sleep(0.5)
