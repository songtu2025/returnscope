from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.api_schemas import (
    DashboardCreateRequest,
    DashboardPlanRequest,
    DashboardVersionCreateRequest,
)
from web_backend.dashboard_service import (
    DashboardConflict,
    DashboardNotFound,
    DashboardService,
)


def create_dashboard_router(
    dashboard_service: DashboardService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/dashboard-plans/preflight")
    def preflight_dashboard(
        payload: DashboardPlanRequest,
        _user: User,
    ) -> dict[str, Any]:
        try:
            return dashboard_service.preflight(
                payload.result_version_ids,
                payload.filters,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/analysis-dashboards", status_code=201)
    def create_dashboard(
        payload: DashboardCreateRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return dashboard_service.create(
                **payload.model_dump(),
                actor_id=str(user["id"]),
            )
        except DashboardConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/analysis-dashboards/{dashboard_id}/versions", status_code=201)
    def create_dashboard_version(
        dashboard_id: str,
        payload: DashboardVersionCreateRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return dashboard_service.create_version(
                dashboard_id,
                **payload.model_dump(),
                actor_id=str(user["id"]),
            )
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DashboardConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards")
    def list_dashboards(
        _user: User,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        q: str | None = Query(default=None),
        status: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.list(
                page=page,
                page_size=page_size,
                q=q,
                status=status,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards/{dashboard_id}")
    def get_dashboard(
        dashboard_id: str,
        _user: User,
        version_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.get(dashboard_id, version_id)
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards/{dashboard_id}/versions")
    def list_dashboard_versions(
        dashboard_id: str,
        _user: User,
    ) -> list[dict[str, Any]]:
        try:
            return dashboard_service.versions(dashboard_id)
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/summary")
    def get_dashboard_summary(
        dashboard_id: str,
        version_id: str,
        _user: User,
    ) -> dict[str, Any]:
        try:
            return dashboard_service.summary(dashboard_id, version_id)
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/sources")
    def get_dashboard_sources(
        dashboard_id: str,
        version_id: str,
        _user: User,
    ) -> list[dict[str, Any]]:
        try:
            return dashboard_service.sources(dashboard_id, version_id)
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/insights"
    )
    def get_dashboard_insights(
        dashboard_id: str,
        version_id: str,
        _user: User,
        problem: str | None = Query(default=None),
        label_group: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.insights(
                dashboard_id,
                version_id,
                problem=problem,
                label_group=label_group,
                listing=listing,
                product_name=product_name,
                product_sku=product_sku,
                date_from=date_from,
                date_to=date_to,
            )
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get(
        "/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/drilldown"
    )
    def get_dashboard_drilldown(
        dashboard_id: str,
        version_id: str,
        _user: User,
        group_by: str = Query(),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        problem: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        order_id: str | None = Query(default=None),
        quality_status: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.drilldown(
                dashboard_id,
                version_id,
                group_by,
                page=page,
                page_size=page_size,
                problem=problem,
                listing=listing,
                product_name=product_name,
                product_sku=product_sku,
                order_id=order_id,
                quality_status=quality_status,
            )
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/records")
    def list_dashboard_records(
        dashboard_id: str,
        version_id: str,
        _user: User,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        problem: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        order_id: str | None = Query(default=None),
        quality_status: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.records(
                dashboard_id,
                version_id,
                page=page,
                page_size=page_size,
                problem=problem,
                listing=listing,
                product_name=product_name,
                product_sku=product_sku,
                order_id=order_id,
                quality_status=quality_status,
            )
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
