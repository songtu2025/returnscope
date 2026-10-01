from datetime import date
from typing import Any, Callable

from fastapi import APIRouter

from web_backend.analysis_service import AnalysisFilters, AnalysisService
from web_backend.routers.task_analysis_routes import register_task_analysis_routes
from web_backend.routers.task_download_routes import register_task_download_routes
from web_backend.routers.task_event_routes import register_task_event_routes
from web_backend.routers.task_lifecycle_routes import (
    register_task_detail_routes,
    register_task_restart_routes,
    register_task_stop_routes,
)
from web_backend.routers.task_planning_routes import (
    register_task_collection_routes,
    register_task_replan_routes,
)
from web_backend.routers.task_segment_routes import (
    register_segment_control_routes,
    register_segment_retry_routes,
)
from web_backend.task_service import (
    TaskService,
)


def analysis_filters(
    start_date: date | None = None,
    end_date: date | None = None,
    category_a: str | None = None,
    category_b: str | None = None,
    listing: str | None = None,
    sku: str | None = None,
    asin: str | None = None,
    reason: str | None = None,
    status: str | None = None,
    problem_code: str | None = None,
    claim_relation: str | None = None,
    dimension: str = "listing",
    focus_problem: str | None = None,
    page: int = 1,
    page_size: int = 50,
    view: str = "all",
) -> AnalysisFilters:
    return AnalysisFilters(
        start_date=start_date,
        end_date=end_date,
        category_a=category_a,
        category_b=category_b,
        listing=listing,
        sku=sku,
        asin=asin,
        reason=reason,
        status=status,
        problem_code=problem_code,
        claim_relation=claim_relation,
        dimension=dimension,
        focus_problem=focus_problem,
        page=page,
        page_size=page_size,
        view=view,
    )


def create_task_router(
    task_service: TaskService,
    analysis_service: AnalysisService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    register_task_collection_routes(router, task_service, current_user)
    register_task_replan_routes(router, task_service, current_user)
    register_segment_retry_routes(router, task_service, current_user)
    register_segment_control_routes(router, task_service, current_user)
    register_task_analysis_routes(
        router, analysis_service, current_user, analysis_filters
    )
    register_task_detail_routes(router, task_service, current_user)
    register_task_stop_routes(router, task_service, current_user)
    register_task_restart_routes(router, task_service, current_user)
    register_task_event_routes(router, task_service, current_user)
    register_task_download_routes(router, task_service, current_user)
    return router
