from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

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
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        order_id: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        source_sku: str | None = Query(default=None),
        matched_msku: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        asin: str | None = Query(default=None),
        problem: str | None = Query(default=None),
        quality_status: str | None = Query(default=None),
        comment_status: str | None = Query(default=None),
        system_rerun_required: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return result_service.records(
                version_id,
                page=page,
                page_size=page_size,
                order_id=order_id,
                listing=listing,
                product_name=product_name,
                source_sku=source_sku,
                matched_msku=matched_msku,
                product_sku=product_sku,
                asin=asin,
                problem=problem,
                quality_status=quality_status,
                comment_status=comment_status,
                system_rerun_required=system_rerun_required,
            )
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
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        order_id: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        source_sku: str | None = Query(default=None),
        matched_msku: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        asin: str | None = Query(default=None),
        problem: str | None = Query(default=None),
        quality_status: str | None = Query(default=None),
        comment_status: str | None = Query(default=None),
        system_rerun_required: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return result_service.record_groups(
                version_id,
                page=page,
                page_size=page_size,
                order_id=order_id,
                listing=listing,
                product_name=product_name,
                source_sku=source_sku,
                matched_msku=matched_msku,
                product_sku=product_sku,
                asin=asin,
                problem=problem,
                quality_status=quality_status,
                comment_status=comment_status,
                system_rerun_required=system_rerun_required,
            )
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
        group_by: str = Query(),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        problem: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        order_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return result_service.drilldown(
                version_id,
                group_by,
                page=page,
                page_size=page_size,
                problem=problem,
                product_name=product_name,
                product_sku=product_sku,
                order_id=order_id,
            )
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
