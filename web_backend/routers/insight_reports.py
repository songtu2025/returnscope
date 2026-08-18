from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.api_schemas import (
    InsightReportFromResultsRequest,
    InsightReportGenerateRequest,
)
from web_backend.dashboard_service import DashboardConflict, DashboardNotFound
from web_backend.insight_report_service import (
    InsightReportConflict,
    InsightReportNotFound,
    InsightReportService,
)


def create_insight_report_router(
    service: InsightReportService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/ai-insight-reports/from-results", status_code=201)
    def create_report_from_results(
        payload: InsightReportFromResultsRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.create_from_results(
                **payload.model_dump(),
                actor_id=str(user["id"]),
            )
        except (DashboardConflict, InsightReportConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post(
        "/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/"
        "ai-insight-reports",
        status_code=201,
    )
    def create_report_for_dashboard(
        dashboard_id: str,
        version_id: str,
        payload: InsightReportGenerateRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.create_for_dashboard(
                dashboard_id,
                version_id,
                **payload.model_dump(),
                actor_id=str(user["id"]),
            )
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InsightReportConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards/{dashboard_id}/ai-insight-reports")
    def list_reports(
        dashboard_id: str,
        _user: User,
        version_id: str = Query(min_length=1),
    ) -> list[dict[str, Any]]:
        try:
            return service.list(dashboard_id, version_id)
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/ai-insight-reports/{report_id}")
    def get_report(report_id: str, _user: User) -> dict[str, Any]:
        try:
            return service.get(report_id)
        except InsightReportNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/ai-insight-reports/{report_id}/retry")
    def retry_report(report_id: str, user: User) -> dict[str, Any]:
        try:
            return service.retry(report_id, str(user["id"]))
        except InsightReportNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InsightReportConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
