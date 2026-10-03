from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from fastapi import APIRouter

from web_backend.config_service import ConfigService
from web_backend.routers.model_catalog_routes import register_model_catalog_routes
from web_backend.routers.model_config_routes import register_model_config_routes
from web_backend.routers.model_validation_routes import register_model_validation_routes


def create_model_router(
    config_service: ConfigService,
    validation_executor: ThreadPoolExecutor,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    register_model_config_routes(
        router, config_service, validation_executor, current_user
    )
    register_model_catalog_routes(
        router, config_service, validation_executor, current_user
    )
    register_model_validation_routes(router, config_service, current_user)
    return router
