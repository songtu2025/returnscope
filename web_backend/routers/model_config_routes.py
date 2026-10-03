from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends

from web_backend.api_contracts.models import ConfigVersionRequest
from web_backend.config_service import ConfigService
from web_backend.routers.model_route_support import (
    model_request_errors,
    require_model_admin,
)


def register_model_config_routes(
    router: APIRouter,
    config_service: ConfigService,
    validation_executor: ThreadPoolExecutor,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/configs")
    def list_configs(_user: User) -> list[dict[str, Any]]:
        return config_service.list()

    @router.post("/api/configs", status_code=201)
    def create_config(payload: ConfigVersionRequest, user: User) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.create_version(
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )

    @router.post("/api/configs/{version_id}/validate")
    def validate_config(version_id: str, user: User) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.validate(version_id, str(user["id"]))

    @router.delete("/api/configs/{version_id}")
    def discard_config(version_id: str, user: User) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.discard_draft(version_id, str(user["id"]))

    @router.post("/api/configs/{version_id}/validation-runs", status_code=201)
    def start_config_validation(
        version_id: str,
        user: User,
    ) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            run = config_service.start_config_validation(
                version_id,
                str(user["id"]),
            )
        validation_executor.submit(config_service.run_validation, run["id"])
        return run

    @router.post("/api/configs/{version_id}/publish")
    def publish_config(version_id: str, user: User) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.publish(version_id, str(user["id"]))
