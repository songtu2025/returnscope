"""沿用普通用户共享复核权限，后端执行范围与版本校验。"""

from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.api_contracts.classification_results import (
    ClassificationResultVersionResponse,
)
from web_backend.api_contracts.manual_correction import ManualCorrectionRequest
from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
    ResultPublicationConflict,
)
from web_backend.classification_results.manual_correction import correct_group


def register_result_correction_routes(
    router: APIRouter,
    service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    @router.patch(
        "/api/classification-results/{version_id}/records/{record_id}/semantics",
        response_model=ClassificationResultVersionResponse,
        response_model_exclude_unset=True,
    )
    def correct_record(
        version_id: str,
        record_id: str,
        payload: ManualCorrectionRequest,
        user: Annotated[dict[str, Any], Depends(current_user)],
    ) -> dict[str, Any]:
        try:
            return correct_group(
                service,
                version_id,
                record_id,
                [item.model_dump() for item in payload.semantic_items],
                str(user["id"]),
            )
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ResultPublicationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
