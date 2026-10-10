from __future__ import annotations

from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.api_contracts.classification_result_queries import (
    ResultDrilldownQuery,
    ResultRecordQuery,
)
from web_backend.api_contracts.classification_results import (
    ClassificationResultDrilldownResponse,
    ClassificationResultGroupsResponse,
    ClassificationResultRecordsResponse,
)
from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
)


def register_result_record_routes(
    router: APIRouter,
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    @router.get(
        "/api/classification-results/{version_id}/records",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultRecordsResponse,
        response_model_exclude_unset=True,
    )
    def list_records(
        version_id: str,
        query: Annotated[ResultRecordQuery, Query()],
    ) -> dict[str, Any]:
        try:
            return result_service.records(version_id, **query.model_dump())
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get(
        "/api/classification-results/{version_id}/record-groups",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultGroupsResponse,
        response_model_exclude_unset=True,
    )
    def list_record_groups(
        version_id: str,
        query: Annotated[ResultRecordQuery, Query()],
    ) -> dict[str, Any]:
        try:
            return result_service.record_groups(version_id, **query.model_dump())
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get(
        "/api/classification-results/{version_id}/drilldown",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultDrilldownResponse,
        response_model_exclude_unset=True,
    )
    def get_drilldown(
        version_id: str,
        query: Annotated[ResultDrilldownQuery, Query()],
    ) -> dict[str, Any]:
        try:
            return result_service.drilldown(
                version_id, query.group_by, **query.model_dump(exclude={"group_by"})
            )
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
