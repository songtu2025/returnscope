from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.data_quality_service import DataQualityService
from web_backend.import_rule_service import list_import_rules
from web_backend.operations_service import AuditLogService, WorkbenchService


def create_operations_router(
    workbench_service: WorkbenchService,
    data_quality_service: DataQualityService,
    audit_log_service: AuditLogService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/workbench/summary")
    def workbench_summary(
        _user: User,
        limit: int = Query(default=5, ge=1, le=20),
    ) -> dict[str, Any]:
        return workbench_service.summary(limit)

    @router.get("/api/import-rules")
    def import_rules(_user: User) -> dict[str, Any]:
        return list_import_rules()

    @router.get("/api/data-quality/preflight")
    def data_quality_preflight(
        _user: User,
        returns_version_id: str = Query(min_length=1),
        products_version_id: str = Query(min_length=1),
    ) -> dict[str, Any]:
        try:
            return data_quality_service.preflight(
                returns_version_id,
                products_version_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/data-quality/issues")
    def data_quality_issues(
        _user: User,
        returns_version_id: str = Query(min_length=1),
        products_version_id: str = Query(min_length=1),
        issue_type: str | None = Query(default=None),
        q: str | None = Query(default=None, max_length=100),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return data_quality_service.issues(
                returns_version_id,
                products_version_id,
                issue_type=issue_type,
                q=q,
                page=page,
                page_size=page_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/audit-logs")
    def list_audit_logs(
        _user: User,
        actor_id: str | None = Query(default=None),
        entity_type: str | None = Query(default=None),
        entity_id: str | None = Query(default=None),
        action: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return audit_log_service.list(
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                date_from=date_from,
                date_to=date_to,
                page=page,
                page_size=page_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
