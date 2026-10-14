"""沿用普通用户共享复核权限，后端执行范围与版本校验。"""

from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.api_contracts.classification_results import (
    ClassificationResultVersionResponse,
)
from web_backend.api_contracts.manual_correction import (
    ManualCorrectionRequest,
    SemanticRestoreRequest,
)
from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
    ResultPublicationConflict,
)
from web_backend.classification_results.manual_correction import (
    _group_members,
    correct_group,
)
from web_backend.classification_results.semantic_history import (
    SemanticRestore,
    correction_history,
)


def register_result_correction_routes(
    router: APIRouter,
    service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get(
        "/api/classification-results/{version_id}/records/{record_id}/corrections"
    )
    def history(version_id: str, record_id: str, _user: User) -> list[dict[str, Any]]:
        try:
            with service.database.connect() as connection:
                base = service._get_version_with_connection(connection, version_id)
                members = _group_members(connection, version_id, record_id)
                return correction_history(
                    connection,
                    base["result_id"],
                    [member["source_row"] for member in members],
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post(
        "/api/classification-results/{version_id}/records/{record_id}/restore-semantics"
    )
    def restore(
        version_id: str, record_id: str, payload: SemanticRestoreRequest, user: User
    ) -> dict[str, Any]:
        try:
            return correct_group(
                service,
                version_id,
                record_id,
                SemanticRestore(payload.audit_id),
                str(user["id"]),
            )
        except ResultPublicationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
