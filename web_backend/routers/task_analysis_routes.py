from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from web_backend.analysis_service import AnalysisFilters, AnalysisService


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
        try:
            return analysis_service.get(task_id, filters)
        except ValueError as exc:
            status_code = 404 if str(exc) == "任务不存在" else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @router.get("/api/tasks/{task_id}/analysis/download")
    def download_filtered_analysis(
        task_id: str,
        _user: User,
        filters: Annotated[AnalysisFilters, Depends(analysis_filters)],
    ) -> Response:
        try:
            content, filename = analysis_service.export_filtered(task_id, filters)
        except ValueError as exc:
            status_code = 404 if str(exc) == "任务不存在" else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
