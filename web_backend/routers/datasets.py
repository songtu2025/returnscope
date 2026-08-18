import secrets
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from web_backend.api_schemas import (
    CategoryCompletionRequest,
    DimensionRowUpdateRequest,
)
from web_backend.dataset_service import DatasetRevisionConflict, DatasetService
from web_backend.settings import Settings

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                output.close()
                destination.unlink(missing_ok=True)
                raise ValueError("单个文件不能超过 200 MB")
            output.write(chunk)


def create_dataset_router(
    dataset_service: DatasetService,
    settings: Settings,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/datasets")
    def list_datasets(
        user: User,
        kind: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        _ = user
        return dataset_service.list(kind)

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

    @router.get("/api/datasets/{dataset_id}")
    def get_dataset(dataset_id: str, _user: User) -> dict[str, Any]:
        dataset = dataset_service.get(dataset_id)
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

    @router.post("/api/datasets", status_code=201)
    async def create_dataset(
        user: User,
        name: Annotated[str, Form(min_length=1, max_length=100)],
        kind: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        description: Annotated[str, Form(max_length=500)] = "",
        change_note: Annotated[str, Form(max_length=500)] = "",
        default_store: Annotated[str, Form(max_length=100)] = "",
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "upload").suffix.lower()
        temp_path = settings.data_dir / "tmp" / f"{secrets.token_hex(12)}{suffix}"
        try:
            await _save_upload(file, temp_path)
            return dataset_service.create(
                name=name,
                kind=kind,
                description=description,
                source_path=temp_path,
                original_name=file.filename or temp_path.name,
                content_type=file.content_type or "application/octet-stream",
                change_note=change_note,
                actor_id=str(user["id"]),
                default_store=default_store,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @router.post("/api/datasets/{dataset_id}/versions", status_code=201)
    async def add_dataset_version(
        dataset_id: str,
        user: User,
        file: Annotated[UploadFile, File()],
        change_note: Annotated[str, Form(min_length=1, max_length=500)],
        default_store: Annotated[str, Form(max_length=100)] = "",
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "upload").suffix.lower()
        temp_path = settings.data_dir / "tmp" / f"{secrets.token_hex(12)}{suffix}"
        try:
            await _save_upload(file, temp_path)
            return dataset_service.add_version(
                dataset_id=dataset_id,
                source_path=temp_path,
                original_name=file.filename or temp_path.name,
                content_type=file.content_type or "application/octet-stream",
                change_note=change_note,
                actor_id=str(user["id"]),
                default_store=default_store,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

    @router.get("/api/datasets/{dataset_id}/rows")
    def preview_dataset_rows(
        dataset_id: str,
        _user: User,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
        q: str = Query(default="", max_length=100),
        store: str = Query(default="", max_length=100),
        category: str = Query(default="", max_length=200),
    ) -> dict[str, Any]:
        try:
            return dataset_service.preview_rows(
                dataset_id,
                offset,
                limit,
                q,
                store,
                category,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/api/datasets/{dataset_id}/rows")
    def update_dimension_row(
        dataset_id: str,
        payload: DimensionRowUpdateRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return dataset_service.update_product_row(
                dataset_id=dataset_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except DatasetRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/datasets/{dataset_id}/category-completion")
    def complete_product_categories(
        dataset_id: str,
        payload: CategoryCompletionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return dataset_service.complete_product_categories(
                dataset_id=dataset_id,
                actor_id=str(user["id"]),
                expected_version=payload.expected_version,
                store=payload.store,
                items=[item.model_dump() for item in payload.items],
                change_note=payload.change_note,
            )
        except DatasetRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
