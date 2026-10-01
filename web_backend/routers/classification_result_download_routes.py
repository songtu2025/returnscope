from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Response

from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
)


def register_result_download_routes(
    router: APIRouter,
    result_service: ClassificationResultService,
    current_user: Callable[..., dict[str, Any]],
    xlsx_media_type: str,
) -> None:
    @router.get(
        "/api/classification-results/{version_id}/download",
        dependencies=[Depends(current_user)],
        response_class=Response,
        responses={200: {"content": {xlsx_media_type: {}}}},
    )
    def download_result(version_id: str) -> Response:
        try:
            content, filename = result_service.download(version_id)
        except ClassificationResultNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=xlsx_media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
