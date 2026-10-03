from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends

from web_backend.api_contracts.models import (
    ModelDefinitionRequest,
    ModelUpdateRequest,
    ModelValidateRequest,
)
from web_backend.config_service import ConfigService
from web_backend.routers.model_route_support import (
    model_request_errors,
    require_model_admin,
)


def register_model_catalog_routes(
    router: APIRouter,
    config_service: ConfigService,
    validation_executor: ThreadPoolExecutor,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/connections/{connection_id}/models", status_code=201)
    def create_model(
        connection_id: str,
        payload: ModelDefinitionRequest,
        user: User,
    ) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.add_model(
                connection_id=connection_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )

    @router.post("/api/connections/{connection_id}/models/discover")
    def discover_models(connection_id: str, user: User) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.sync_models_from_provider(
                connection_id,
                str(user["id"]),
            )

    @router.patch("/api/models/{model_id}")
    def update_model(
        model_id: str,
        payload: ModelUpdateRequest,
        user: User,
    ) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.update_model(
                model_id=model_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )

    @router.post("/api/models/{model_id}/validate")
    def validate_model(
        model_id: str,
        user: User,
        payload: ModelValidateRequest | None = None,
    ) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            return config_service.validate_model(
                model_id,
                str(user["id"]),
                payload.effort if payload else None,
            )

    @router.post("/api/models/{model_id}/validation-runs", status_code=201)
    def start_model_validation(
        model_id: str,
        user: User,
        payload: ModelValidateRequest | None = None,
    ) -> dict[str, Any]:
        require_model_admin(user)
        with model_request_errors():
            run = config_service.start_model_validation(
                model_id,
                str(user["id"]),
                payload.effort if payload else None,
            )
        validation_executor.submit(config_service.run_validation, run["id"])
        return run
