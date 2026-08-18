import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, AsyncIterator, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from web_backend.api_schemas import (
    ConfigVersionRequest,
    ModelDefinitionRequest,
    ModelUpdateRequest,
    ModelValidateRequest,
)
from web_backend.config_service import ConfigService


def create_model_router(
    config_service: ConfigService,
    validation_executor: ThreadPoolExecutor,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    def require_admin(user: dict[str, Any]) -> None:
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="仅系统管理员可维护模型服务")

    @router.get("/api/configs")
    def list_configs(_user: User) -> list[dict[str, Any]]:
        return config_service.list()

    @router.post("/api/connections/{connection_id}/models", status_code=201)
    def create_model(
        connection_id: str,
        payload: ModelDefinitionRequest,
        user: User,
    ) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.add_model(
                connection_id=connection_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/connections/{connection_id}/models/discover")
    def discover_models(connection_id: str, user: User) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.sync_models_from_provider(
                connection_id,
                str(user["id"]),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/api/models/{model_id}")
    def update_model(
        model_id: str,
        payload: ModelUpdateRequest,
        user: User,
    ) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.update_model(
                model_id=model_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/models/{model_id}/validate")
    def validate_model(
        model_id: str,
        user: User,
        payload: ModelValidateRequest | None = None,
    ) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.validate_model(
                model_id,
                str(user["id"]),
                payload.effort if payload else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/models/{model_id}/validation-runs", status_code=201)
    def start_model_validation(
        model_id: str,
        user: User,
        payload: ModelValidateRequest | None = None,
    ) -> dict[str, Any]:
        require_admin(user)
        try:
            run = config_service.start_model_validation(
                model_id,
                str(user["id"]),
                payload.effort if payload else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        validation_executor.submit(config_service.run_validation, run["id"])
        return run

    @router.post("/api/configs", status_code=201)
    def create_config(payload: ConfigVersionRequest, user: User) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.create_version(
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/configs/{version_id}/validate")
    def validate_config(version_id: str, user: User) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.validate(version_id, str(user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/api/configs/{version_id}")
    def discard_config(version_id: str, user: User) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.discard_draft(version_id, str(user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/configs/{version_id}/validation-runs", status_code=201)
    def start_config_validation(
        version_id: str,
        user: User,
    ) -> dict[str, Any]:
        require_admin(user)
        try:
            run = config_service.start_config_validation(
                version_id,
                str(user["id"]),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        validation_executor.submit(config_service.run_validation, run["id"])
        return run

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

        async def event_stream() -> AsyncIterator[str]:
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

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/api/configs/{version_id}/publish")
    def publish_config(version_id: str, user: User) -> dict[str, Any]:
        require_admin(user)
        try:
            return config_service.publish(version_id, str(user["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
