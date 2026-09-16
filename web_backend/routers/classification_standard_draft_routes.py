import json
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from web_backend.api_schemas import (
    ClassificationStandardDraftActionRequest,
    ClassificationStandardDraftImportRequest,
    ClassificationStandardDraftRevisionRequest,
    ClassificationStandardDraftUpdateRequest,
)
from web_backend.classification_standard_service import ClassificationStandardService


class _DraftOperations:
    def __init__(
        self,
        service: ClassificationStandardService,
        handle_error: Callable[[ValueError], HTTPException],
    ) -> None:
        self.service = service
        self.handle_error = handle_error

    def create_draft(self, standard_id: str, user: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.service.create_draft(standard_id, str(user["id"]))
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        try:
            return self.service.get_draft(draft_id)
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def update_draft(
        self,
        draft_id: str,
        payload: ClassificationStandardDraftUpdateRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.service.update_draft(
                draft_id,
                payload.expected_revision,
                payload.content.model_dump(),
                payload.change_reason,
                str(user["id"]),
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def import_draft(
        self,
        draft_id: str,
        payload: ClassificationStandardDraftImportRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.service.import_draft_document(
                draft_id,
                payload.expected_revision,
                payload.document.model_dump(),
                payload.change_reason,
                str(user["id"]),
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    async def preview_draft_excel(
        self,
        draft_id: str,
        file: UploadFile,
        sheet_name: str,
        columns_json: str,
    ) -> dict[str, Any]:
        try:
            content = await file.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise ValueError("标签框架文件不能超过20MB")
            columns = json.loads(columns_json)
            if not isinstance(columns, dict):
                raise ValueError("列映射必须为 JSON 对象")
            return self.service.preview_draft_excel(
                draft_id, content, sheet_name, columns
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def validate_draft(
        self,
        draft_id: str,
        payload: ClassificationStandardDraftRevisionRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.service.validate_draft(
                draft_id, payload.expected_revision, str(user["id"])
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def publish_draft(
        self,
        draft_id: str,
        payload: ClassificationStandardDraftActionRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.service.publish_draft(
                draft_id, payload.expected_revision, payload.reason, str(user["id"])
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def discard_draft(
        self,
        draft_id: str,
        payload: ClassificationStandardDraftActionRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.service.discard_draft(
                draft_id, payload.expected_revision, payload.reason, str(user["id"])
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc


def register_draft_routes(
    router: APIRouter,
    service: ClassificationStandardService,
    current_user: Callable[..., dict[str, Any]],
    handle_error: Callable[[ValueError], HTTPException],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]
    operations = _DraftOperations(service, handle_error)

    @router.post("/api/classification-standards/{standard_id}/draft", status_code=201)
    def create_draft(standard_id: str, user: User) -> dict[str, Any]:
        return operations.create_draft(standard_id, user)

    @router.get("/api/classification-standard-drafts/{draft_id}")
    def get_draft(draft_id: str, _user: User) -> dict[str, Any]:
        return operations.get_draft(draft_id)

    @router.patch("/api/classification-standard-drafts/{draft_id}")
    def update_draft(
        draft_id: str,
        payload: ClassificationStandardDraftUpdateRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.update_draft(draft_id, payload, user)

    @router.post("/api/classification-standard-drafts/{draft_id}/import")
    def import_draft(
        draft_id: str,
        payload: ClassificationStandardDraftImportRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.import_draft(draft_id, payload, user)

    @router.post("/api/classification-standard-drafts/{draft_id}/preview-excel")
    async def preview_draft_excel(
        draft_id: str,
        _user: User,
        file: Annotated[UploadFile, File()],
        sheet_name: Annotated[str, Form()] = "",
        columns_json: Annotated[str, Form()] = "{}",
    ) -> dict[str, Any]:
        return await operations.preview_draft_excel(
            draft_id, file, sheet_name, columns_json
        )

    @router.post("/api/classification-standard-drafts/{draft_id}/validate")
    def validate_draft(
        draft_id: str,
        payload: ClassificationStandardDraftRevisionRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.validate_draft(draft_id, payload, user)

    @router.post("/api/classification-standard-drafts/{draft_id}/publish")
    def publish_draft(
        draft_id: str,
        payload: ClassificationStandardDraftActionRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.publish_draft(draft_id, payload, user)

    @router.post("/api/classification-standard-drafts/{draft_id}/discard")
    def discard_draft(
        draft_id: str,
        payload: ClassificationStandardDraftActionRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.discard_draft(draft_id, payload, user)
