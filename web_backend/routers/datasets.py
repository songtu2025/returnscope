import secrets
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from web_backend.api_schemas import (
    CategoryCompletionRequest,
    DatasetStorageCleanupRequest,
    DimensionRowUpdateRequest,
    MySQLReturnImportRequest,
    ReturnImportRequest,
)
from web_backend.dataset_service import DatasetRevisionConflict, DatasetService
from web_backend.mysql_return_service import MySQLReturnService, MySQLSourceError
from web_backend.settings import Settings

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload_content_type(upload: UploadFile, suffix: str) -> str:
    if upload.content_type:
        return upload.content_type
    return {".csv": "text/csv", ".xlsx": XLSX_CONTENT_TYPE}.get(
        suffix,
        "application/octet-stream",
    )


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
    mysql_service = MySQLReturnService(dataset_service, settings)

    @router.get("/api/mysql-return-imports/schema")
    def mysql_return_schema(
        _user: User, refresh: bool = Query(default=False)
    ) -> dict[str, Any]:
        try:
            return mysql_service.schema(refresh=refresh)
        except MySQLSourceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/api/mysql-return-imports/preview")
    def preview_mysql_returns(
        payload: MySQLReturnImportRequest, _user: User
    ) -> dict[str, Any]:
        try:
            return mysql_service.preview(payload)
        except MySQLSourceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/mysql-return-imports", status_code=201)
    def import_mysql_returns(
        payload: MySQLReturnImportRequest, user: User
    ) -> dict[str, Any]:
        try:
            return mysql_service.import_returns(payload, str(user["id"]))
        except MySQLSourceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    @router.get("/api/dataset-storage")
    def dataset_storage_summary(
        _user: User,
        dataset_ids: str = Query(min_length=1, max_length=10000),
        retention_days: int = Query(default=30, ge=7, le=3650),
        retain_latest: int = Query(default=2, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            return dataset_service.storage_summary(
                dataset_ids=dataset_ids.split(","),
                retention_days=retention_days,
                retain_latest=retain_latest,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/dataset-storage/cleanup")
    def cleanup_dataset_storage(
        payload: DatasetStorageCleanupRequest,
        user: User,
    ) -> dict[str, Any]:
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="仅系统管理员可清理快照存储")
        try:
            return dataset_service.cleanup_storage(
                dataset_ids=payload.dataset_ids,
                retention_days=payload.retention_days,
                retain_latest=payload.retain_latest,
                actor_id=str(user["id"]),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/return-imports/inspect")
    async def inspect_return_import(
        user: User,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "upload").suffix.lower()
        temp_path = (
            settings.data_dir
            / "tmp"
            / "dataset-imports"
            / f"{secrets.token_hex(12)}{suffix}"
        )
        try:
            await _save_upload(file, temp_path)
            return dataset_service.inspect_return_import(
                temp_path,
                file.filename or temp_path.name,
                actor_id=str(user["id"]),
                content_type=_upload_content_type(file, suffix),
            )
        except ValueError as exc:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    @router.post("/api/return-imports", status_code=201)
    def import_returns(
        user: User,
        payload: ReturnImportRequest,
    ) -> dict[str, Any]:
        try:
            return dataset_service.import_staged_returns(
                inspection_id=payload.inspection_id,
                actor_id=str(user["id"]),
                mode=payload.mode,
                dataset_id=payload.dataset_id,
                name=payload.name,
                change_note=payload.change_note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
                content_type=_upload_content_type(file, suffix),
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
                content_type=_upload_content_type(file, suffix),
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
        version: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        try:
            return dataset_service.preview_rows(
                dataset_id=dataset_id,
                offset=offset,
                limit=limit,
                query=q,
                store=store,
                category=category,
                version=version,
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
