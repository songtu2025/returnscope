from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from web_backend.dataset_service import DatasetService


def _register_dataset_version_queries(
    router: APIRouter,
    dataset_service: DatasetService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/datasets")
    def list_datasets(
        user: User,
        kind: str | None = Query(default=None),
        usage_scope: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        _ = user
        return dataset_service.list(kind, usage_scope)

    @router.get("/api/data-versions")
    def list_data_versions(
        _user: User,
        kind: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        return dataset_service.list_versions(kind)

    @router.get("/api/data-versions/{version_id}/references")
    def list_data_version_references(
        version_id: str,
        _user: User,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return dataset_service.references(
                version_id,
                page=page,
                page_size=page_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/data-versions/{version_id}/scopes")
    def list_product_scopes(
        version_id: str,
        _user: User,
    ) -> list[dict[str, Any]]:
        try:
            return dataset_service.product_scopes(version_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _register_dataset_read_routes(
    router: APIRouter,
    dataset_service: DatasetService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/datasets/{dataset_id}")
    def get_dataset(
        dataset_id: str,
        _user: User,
        include: str | None = Query(default=None, max_length=100),
    ) -> dict[str, Any]:
        requested = None
        if include is not None:
            requested = {value.strip() for value in include.split(",") if value.strip()}
            if not requested.issubset({"versions", "imports", "audit"}):
                raise HTTPException(status_code=400, detail="include 参数不合法")
        dataset = dataset_service.get(dataset_id, requested)
        if dataset is None:
            raise HTTPException(status_code=404, detail="数据集不存在")
        return dataset

    @router.get("/api/datasets/{dataset_id}/download")
    def download_dataset_version(
        dataset_id: str,
        _user: User,
        version: int | None = Query(default=None, ge=1),
    ) -> FileResponse:
        item = dataset_service.version_file(dataset_id, version)
        if item is None:
            raise HTTPException(status_code=404, detail="数据版本不存在")
        path = Path(str(item["file_path"]))
        if not path.exists():
            raise HTTPException(status_code=404, detail="数据文件不存在")
        return FileResponse(
            path,
            filename=str(item["original_name"]),
            media_type=str(item["content_type"]),
        )
