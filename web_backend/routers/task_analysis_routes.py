from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from web_backend.analysis_service import AnalysisFilters, AnalysisService
from web_backend.routers.task_route_support import task_analysis_errors


def register_task_analysis_routes(
    router: APIRouter,
    analysis_service: AnalysisService,
    current_user: Callable[..., dict[str, Any]],
    analysis_filters: Callable[..., AnalysisFilters],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/tasks/{task_id}/analysis")
    def get_task_analysis(
        task_id: str,
        _user: User,
        filters: Annotated[AnalysisFilters, Depends(analysis_filters)],
    ) -> dict[str, Any]:
        with task_analysis_errors():
            return analysis_service.get(task_id, filters)

    @router.get("/api/tasks/{task_id}/analysis/download")
    def download_filtered_analysis(
        task_id: str,
        _user: User,
        filters: Annotated[AnalysisFilters, Depends(analysis_filters)],
    ) -> Response:
        with task_analysis_errors():
            content, filename = analysis_service.export_filtered(task_id, filters)
        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
