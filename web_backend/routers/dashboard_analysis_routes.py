from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.dashboard_insights import InsightOptions
from web_backend.dashboard_service import DashboardNotFound, DashboardService


def _register_dashboard_analysis(
    router: APIRouter,
    dashboard_service: DashboardService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

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
        subject: str | None = Query(default=None),
        label_group: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        part: str = Query(default="full", pattern="^(full|overview|reason)$"),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.insights(
                dashboard_id,
                version_id,
                problem=problem,
                subject=subject,
                label_group=label_group,
                listing=listing,
                product_name=product_name,
                product_sku=product_sku,
                date_from=date_from,
                date_to=date_to,
                part=part,
            )
        except DashboardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _register_dashboard_evidence(
    router: APIRouter,
    dashboard_service: DashboardService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get(
        "/api/analysis-dashboards/{dashboard_id}/versions/{version_id}/evidence"
    )
    def get_dashboard_evidence(
        dashboard_id: str,
        version_id: str,
        _user: User,
        problem: str = Query(),
        page: int = Query(default=1, ge=1),
        subject: str | None = Query(default=None),
        label_group: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return dashboard_service.evidence_page(
                dashboard_id,
                version_id,
                InsightOptions(
                    problem=problem,
                    subject=subject,
                    label_group=label_group,
                    listing=listing,
                    product_name=product_name,
                    product_sku=product_sku,
                    date_from=date_from,
                    date_to=date_to,
                ),
                page=page,
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
