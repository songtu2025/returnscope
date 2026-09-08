import json
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from web_backend.api_schemas import (
    ClassificationStandardCreateRequest,
    ClassificationStandardDraftActionRequest,
    ClassificationStandardDraftImportRequest,
    ClassificationStandardDraftRevisionRequest,
    ClassificationStandardDraftUpdateRequest,
    ClassificationStandardSampleValidationRequest,
    ClassificationStandardValidationApprovalRequest,
)
from web_backend.classification_standard_service import (
    ClassificationStandardConflict,
    ClassificationStandardNotFound,
    ClassificationStandardService,
    ClassificationStandardValidationError,
)
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationConflict,
    ClassificationStandardValidationNotFound,
    ClassificationStandardValidationService,
)


def create_classification_standard_router(
    service: ClassificationStandardService,
    validation_service: ClassificationStandardValidationService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    def handle_error(exc: ValueError) -> HTTPException:
        if isinstance(exc, ClassificationStandardNotFound):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, ClassificationStandardConflict):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, ClassificationStandardValidationNotFound):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, ClassificationStandardValidationConflict):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, ClassificationStandardValidationError):
            message = "；".join(exc.validation["blocking"])
            return HTTPException(status_code=400, detail=message)
        return HTTPException(status_code=400, detail=str(exc))

    @router.get(
        "/api/classification-standards",
        dependencies=[Depends(current_user)],
    )
    def list_standards() -> list[dict[str, Any]]:
        return service.list()

    @router.post("/api/classification-standards", status_code=201)
    def create_standard(
        payload: ClassificationStandardCreateRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.create_standard(
                name=payload.name,
                product_context=payload.product_context,
                category_a=payload.category_a,
                category_b=payload.category_b,
                actor_id=str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.get(
        "/api/classification-standards/{standard_id}",
        dependencies=[Depends(current_user)],
    )
    def get_standard(standard_id: str) -> dict[str, Any]:
        try:
            return service.get(standard_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/api/classification-standards/{standard_id}")
    def delete_standard(standard_id: str, user: User) -> dict[str, Any]:
        try:
            return service.delete_standard(standard_id, str(user["id"]))
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.get(
        "/api/classification-standards/{standard_id}/versions",
        dependencies=[Depends(current_user)],
    )
    def list_versions(standard_id: str) -> list[dict[str, Any]]:
        try:
            return service.versions(standard_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get(
        "/api/classification-standard-versions/{version_id}",
        dependencies=[Depends(current_user)],
    )
    def get_version(version_id: str) -> dict[str, Any]:
        try:
            return service.get_version(version_id)
        except ClassificationStandardNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/classification-standard-versions/{version_id}/export")
    def export_version(version_id: str, _user: User) -> Response:
        try:
            document = service.export_version_document(version_id)
        except ValueError as exc:
            raise handle_error(exc) from exc
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

    @router.post(
        "/api/classification-standard-versions/{version_id}/restore-draft",
        status_code=201,
    )
    def restore_version_as_draft(version_id: str, user: User) -> dict[str, Any]:
        try:
            return service.restore_version_as_draft(
                version_id,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post("/api/classification-standards/{standard_id}/draft", status_code=201)
    def create_draft(standard_id: str, user: User) -> dict[str, Any]:
        try:
            return service.create_draft(standard_id, str(user["id"]))
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.get("/api/classification-standard-drafts/{draft_id}")
    def get_draft(draft_id: str, _user: User) -> dict[str, Any]:
        try:
            return service.get_draft(draft_id)
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.patch("/api/classification-standard-drafts/{draft_id}")
    def update_draft(
        draft_id: str,
        payload: ClassificationStandardDraftUpdateRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.update_draft(
                draft_id,
                payload.expected_revision,
                payload.content.model_dump(),
                payload.change_reason,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post("/api/classification-standard-drafts/{draft_id}/import")
    def import_draft(
        draft_id: str,
        payload: ClassificationStandardDraftImportRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.import_draft_document(
                draft_id,
                payload.expected_revision,
                payload.document.model_dump(),
                payload.change_reason,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post("/api/classification-standard-drafts/{draft_id}/validate")
    def validate_draft(
        draft_id: str,
        payload: ClassificationStandardDraftRevisionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.validate_draft(
                draft_id,
                payload.expected_revision,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post("/api/classification-standard-drafts/{draft_id}/publish")
    def publish_draft(
        draft_id: str,
        payload: ClassificationStandardDraftActionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.publish_draft(
                draft_id,
                payload.expected_revision,
                payload.reason,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post("/api/classification-standard-drafts/{draft_id}/discard")
    def discard_draft(
        draft_id: str,
        payload: ClassificationStandardDraftActionRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.discard_draft(
                draft_id,
                payload.expected_revision,
                payload.reason,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.get("/api/classification-standard-drafts/{draft_id}/validation-sources")
    def validation_sources(draft_id: str, _user: User) -> list[dict[str, Any]]:
        try:
            return validation_service.sources(draft_id)
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.get("/api/classification-standard-drafts/{draft_id}/validation-runs")
    def validation_runs(draft_id: str, _user: User) -> list[dict[str, Any]]:
        try:
            return validation_service.list_runs(draft_id)
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post(
        "/api/classification-standard-drafts/{draft_id}/validation-runs",
        status_code=201,
    )
    def create_validation_run(
        draft_id: str,
        payload: ClassificationStandardSampleValidationRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return validation_service.create_run(
                draft_id,
                payload.expected_revision,
                payload.source_result_version_id,
                payload.sample_size,
                str(user["id"]),
                comparison_type=payload.comparison_type,
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post(
        "/api/classification-standard-drafts/{draft_id}/review-validation-runs",
        status_code=201,
    )
    async def create_review_validation_run(
        draft_id: str,
        user: User,
        expected_revision: Annotated[int, Form(ge=1)],
        file: Annotated[UploadFile, File()],
        sample_size: Annotated[int, Form()] = 20,
        comparison_type: Annotated[str, Form()] = "standard_version",
    ) -> dict[str, Any]:
        try:
            content = await file.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise ValueError("Review 文件不能超过20MB")
            return validation_service.create_run(
                draft_id,
                expected_revision,
                "",
                sample_size,
                str(user["id"]),
                review_file=(file.filename or "", content),
                comparison_type=comparison_type,
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.get("/api/classification-standard-validation-runs/{run_id}")
    def validation_run(run_id: str, _user: User) -> dict[str, Any]:
        try:
            return validation_service.get(run_id)
        except ValueError as exc:
            raise handle_error(exc) from exc

    @router.post("/api/classification-standard-validation-runs/{run_id}/approve")
    def approve_validation_run(
        run_id: str,
        payload: ClassificationStandardValidationApprovalRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return validation_service.approve(
                run_id,
                payload.expected_revision,
                payload.note,
                str(user["id"]),
            )
        except ValueError as exc:
            raise handle_error(exc) from exc

    return router
