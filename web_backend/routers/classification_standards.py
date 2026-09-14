from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from web_backend.classification_standard_contracts import (
    ClassificationStandardConflict,
    ClassificationStandardNotFound,
    ClassificationStandardValidationError,
)
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationConflict,
    ClassificationStandardValidationNotFound,
    ClassificationStandardValidationService,
)
from web_backend.routers.classification_standard_draft_routes import (
    register_draft_routes,
)
from web_backend.routers.classification_standard_validation_routes import (
    register_validation_routes,
)
from web_backend.routers.classification_standard_version_routes import (
    register_standard_version_routes,
)


def create_classification_standard_router(
    service: ClassificationStandardService,
    validation_service: ClassificationStandardValidationService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    def handle_error(exc: ValueError) -> HTTPException:
        if isinstance(exc, ClassificationStandardNotFound):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, ClassificationStandardConflict):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, ClassificationStandardValidationNotFound):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, ClassificationStandardValidationConflict):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, ClassificationStandardValidationError):
            message = "；".join(exc.validation["blocking"])
            return HTTPException(status_code=400, detail=message)
        return HTTPException(status_code=400, detail=str(exc))

    register_standard_version_routes(router, service, current_user, handle_error)
    register_draft_routes(router, service, current_user, handle_error)
    register_validation_routes(
        router,
        validation_service,
        current_user,
        handle_error,
    )
    return router
