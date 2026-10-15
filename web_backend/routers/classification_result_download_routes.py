from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
)


def register_result_download_routes(
    router: APIRouter,
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    @router.get(
        "/api/classification-results/{version_id}/download",
        dependencies=[Depends(current_user)],
        status_code=410,
        deprecated=True,
        responses={
            410: {"description": "Synchronous download retired; use background export."}
        },
    )
    def download_result(version_id: str) -> None:
        try:
            result_service.get(version_id)
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(
            status_code=410,
            detail="同步下载已停用，请在分类结果页点击下载，后台生成文件。",
        )
