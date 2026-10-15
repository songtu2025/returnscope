"""导出任务提交、恢复查询与私有文件下载。"""

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from web_backend.classification_result_service import ClassificationResultNotFound
from web_backend.classification_results.export_jobs import ResultExportService


class ResultExportResponse(BaseModel):
    id: str
    status: str
    filename: str
    error: str
    expires_at: float


class ResultExportRequest(BaseModel):
    version_ids: list[str] = Field(min_length=1)


def create_result_export_router(
    service: ResultExportService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(current_user)])

    @router.post("/api/result-exports")
    def create_combined_export(payload: ResultExportRequest) -> ResultExportResponse:
        try:
            return ResultExportResponse(**service.create(payload.version_ids))
        except ClassificationResultNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/api/result-exports/{job_id}")
    def get_export(job_id: str) -> ResultExportResponse:
        try:
            return ResultExportResponse(**service.get(job_id))
        except (FileNotFoundError, ClassificationResultNotFound) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get(
        "/api/result-exports/{job_id}/file",
        response_class=FileResponse,
        responses={
            200: {
                "content": {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
                }
            }
        },
    )
    def download_export(job_id: str) -> FileResponse:
        try:
            path, filename = service.file(job_id)
        except (FileNotFoundError, ClassificationResultNotFound) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return FileResponse(
            path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return router
