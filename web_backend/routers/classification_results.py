from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter

from web_backend.classification_result_service import (
    ClassificationResultService,
)
from web_backend.classification_standard_service import (
    ClassificationStandardService,
)
from web_backend.routers.classification_result_download_routes import (
    register_result_download_routes,
)
from web_backend.routers.classification_result_query_routes import (
    register_result_metadata_routes,
    register_result_version_routes,
)
from web_backend.routers.classification_result_record_routes import (
    register_result_record_routes,
)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def create_classification_result_router(
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
    standard_service: ClassificationStandardService | None = None,
) -> APIRouter:
    router = APIRouter()
    standards = standard_service or ClassificationStandardService(
        result_service.database
    )
    register_result_version_routes(router, result_service, current_user)
    register_result_metadata_routes(router, result_service, current_user, standards)
    register_result_record_routes(router, result_service, current_user)
    register_result_download_routes(
        router, result_service, current_user, XLSX_MEDIA_TYPE
    )
    return router
