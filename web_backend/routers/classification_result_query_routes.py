from __future__ import annotations

from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.api_contracts.classification_result_queries import (
    ResultVersionQuery,
)
from web_backend.api_contracts.classification_results import (
    ClassificationResultListResponse,
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


def register_result_version_routes(
    router: APIRouter,
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    @router.get(
        "/api/classification-results",
        dependencies=[Depends(current_user)],
        response_model=ClassificationResultListResponse,
        response_model_exclude_unset=True,
    )
    def list_results(
        query: Annotated[ResultVersionQuery, Query()],
    ) -> dict[str, Any]:
        try:
            return result_service.list(**query.model_dump())
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


def register_result_metadata_routes(
    router: APIRouter,
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
    standards: ClassificationStandardService,
) -> None:
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
