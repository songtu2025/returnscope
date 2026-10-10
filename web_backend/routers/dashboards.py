from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.api_contracts.dashboards import (
    DashboardCreateRequest,
    DashboardPlanRequest,
    DashboardVersionCreateRequest,
)
from web_backend.dashboard_service import (
    DashboardConflict,
    DashboardNotFound,
    DashboardService,
)
from web_backend.routers.dashboard_analysis_routes import (
    _register_dashboard_analysis,
    _register_dashboard_evidence,
)


def create_dashboard_router(
    dashboard_service: DashboardService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    _register_dashboard_creation(router, dashboard_service, current_user)
    _register_dashboard_queries(router, dashboard_service, current_user)
    _register_dashboard_analysis(router, dashboard_service, current_user)
    _register_dashboard_evidence(router, dashboard_service, current_user)
    return router


def _register_dashboard_creation(
    router: APIRouter,
    dashboard_service: DashboardService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
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


def _register_dashboard_queries(
    router: APIRouter,
    dashboard_service: DashboardService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

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
