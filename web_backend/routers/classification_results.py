from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from web_backend.api_schemas import (
    ClassificationResultDrilldownResponse,
    ClassificationResultGroupsResponse,
    ClassificationResultListResponse,
    ClassificationResultRecordsResponse,
    ClassificationResultSummaryResponse,
    ClassificationResultTaxonomyResponse,
    ClassificationResultVersionResponse,
)
from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
)
from web_backend.classification_standard_service import (
    ClassificationStandardNotFound,
    ClassificationStandardService,
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

    @router.get(
        "/api/classification-results",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultListResponse,
        response_model_exclude_unset=True,
    )
    def list_results(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        q: str | None = Query(default=None),
        store_site: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        quality_status: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return result_service.list(
                page=page,
                page_size=page_size,
                q=q,
                store_site=store_site,
                listing=listing,
                quality_status=quality_status,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get(
        "/api/classification-results/{version_id}",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultVersionResponse,
        response_model_exclude_unset=True,
    )
    def get_result(version_id: str) -> dict[str, Any]:
        try:
            return result_service.get(version_id)
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/api/classification-results/{version_id}/versions",
        dependencies=[Depends(current_user)],
        response_model=list[ClassificationResultVersionResponse],
        response_model_exclude_unset=True,
    )
    def get_result_versions(version_id: str) -> list[dict[str, Any]]:
        try:
            return result_service.history(version_id)
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/api/classification-results/{version_id}/taxonomy",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultTaxonomyResponse,
        response_model_exclude_unset=True,
    )
    def get_result_taxonomy(version_id: str) -> dict[str, Any]:
        try:
            return standards.taxonomy_for_result_version(version_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/api/classification-results/{version_id}/summary",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultSummaryResponse,
        response_model_exclude_unset=True,
    )
    def get_summary(version_id: str) -> dict[str, Any]:
        try:
            return result_service.summary(version_id)
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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

    @router.get(
        "/api/classification-results/{version_id}/download",
        dependencies=[Depends(current_user)],
        response_class=Response,
        responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
    )
    def download_result(version_id: str) -> Response:
        try:
            content, filename = result_service.download(version_id)
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
