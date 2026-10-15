from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter

from web_backend.classification_result_service import (
    ClassificationResultService,
)
from web_backend.classification_results.export_jobs import ResultExportService
from web_backend.classification_standard_service import (
    ClassificationStandardService,
)
from web_backend.routers.classification_result_correction_routes import (
    register_result_correction_routes,
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
from web_backend.routers.delivery_lifecycle_routes import register_delivery_actions
from web_backend.routers.result_export_routes import create_result_export_router

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def create_classification_result_router(
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
    standard_service: ClassificationStandardService | None = None,
    export_service: ResultExportService | None = None,
) -> APIRouter:
    router = APIRouter()
    if export_service is not None:
        router.include_router(create_result_export_router(export_service, current_user))
    register_delivery_actions(
        router, lambda: result_service.database, current_user, kind="result"
    )
    standards = standard_service or ClassificationStandardService(
        result_service.database
    )
    register_result_version_routes(router, result_service, current_user)
    register_result_metadata_routes(router, result_service, current_user, standards)
    register_result_record_routes(router, result_service, current_user)
    register_result_correction_routes(router, result_service, current_user)
    register_result_download_routes(
        router, result_service, current_user, XLSX_MEDIA_TYPE
    )
    return router
