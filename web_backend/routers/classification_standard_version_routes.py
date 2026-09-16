import json
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from web_backend.api_schemas import ClassificationStandardCreateRequest
from web_backend.classification_standard_contracts import (
    ClassificationStandardNotFound,
)
from web_backend.classification_standard_service import ClassificationStandardService


class _StandardVersionOperations:
    def __init__(
        self,
        service: ClassificationStandardService,
        handle_error: Callable[[ValueError], HTTPException],
    ) -> None:
        self.service = service
        self.handle_error = handle_error

    def create_standard(
        self, payload: ClassificationStandardCreateRequest, user: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return self.service.create_standard(
                name=payload.name,
                product_context=payload.product_context,
                category_a=payload.category_a,
                category_b=payload.category_b,
                actor_id=str(user["id"]),
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def get_standard(self, standard_id: str) -> dict[str, Any]:
        try:
            return self.service.get(standard_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def delete_standard(self, standard_id: str, user: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.service.delete_standard(standard_id, str(user["id"]))
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def list_versions(self, standard_id: str) -> list[dict[str, Any]]:
        try:
            return self.service.versions(standard_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_version(self, version_id: str) -> dict[str, Any]:
        try:
            return self.service.get_version(version_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def export_version(self, version_id: str) -> Response:
        try:
            document = self.service.export_version_document(version_id)
        except ValueError as exc:
            raise self.handle_error(exc) from exc
        source = document["source"]
        filename = (
            f"{source['standard_key']}-v{source['version_no']}"
            ".classification-standard.json"
        )
        return Response(
            content=json.dumps(document, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def restore_version_as_draft(
        self, version_id: str, user: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return self.service.restore_version_as_draft(version_id, str(user["id"]))
        except ValueError as exc:
            raise self.handle_error(exc) from exc


def register_standard_version_routes(
    router: APIRouter,
    service: ClassificationStandardService,
    current_user: Callable[..., dict[str, Any]],
    handle_error: Callable[[ValueError], HTTPException],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]
    operations = _StandardVersionOperations(service, handle_error)

    @router.get("/api/classification-standards", dependencies=[Depends(current_user)])
    def list_standards() -> list[dict[str, Any]]:
        return service.list()

    @router.post("/api/classification-standards", status_code=201)
    def create_standard(
        payload: ClassificationStandardCreateRequest, user: User
    ) -> dict[str, Any]:
        return operations.create_standard(payload, user)

    @router.get(
        "/api/classification-standards/{standard_id}",
        dependencies=[Depends(current_user)],
    )
    def get_standard(standard_id: str) -> dict[str, Any]:
        return operations.get_standard(standard_id)

    @router.delete("/api/classification-standards/{standard_id}")
    def delete_standard(standard_id: str, user: User) -> dict[str, Any]:
        return operations.delete_standard(standard_id, user)

    @router.get(
        "/api/classification-standards/{standard_id}/versions",
        dependencies=[Depends(current_user)],
    )
    def list_versions(standard_id: str) -> list[dict[str, Any]]:
        return operations.list_versions(standard_id)

    @router.get(
        "/api/classification-standard-versions/{version_id}",
        dependencies=[Depends(current_user)],
    )
    def get_version(version_id: str) -> dict[str, Any]:
        return operations.get_version(version_id)

    @router.get("/api/classification-standard-versions/{version_id}/export")
    def export_version(version_id: str, _user: User) -> Response:
        return operations.export_version(version_id)

    @router.post(
        "/api/classification-standard-versions/{version_id}/restore-draft",
        status_code=201,
    )
    def restore_version_as_draft(version_id: str, user: User) -> dict[str, Any]:
        return operations.restore_version_as_draft(version_id, user)
