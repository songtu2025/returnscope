from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from web_backend.api_schemas import (
    ClassificationStandardSampleValidationRequest,
    ClassificationStandardValidationApprovalRequest,
)
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)


class _ValidationOperations:
    def __init__(
        self,
        validation_service: ClassificationStandardValidationService,
        handle_error: Callable[[ValueError], HTTPException],
    ) -> None:
        self.validation_service = validation_service
        self.handle_error = handle_error

    def validation_sources(self, draft_id: str) -> list[dict[str, Any]]:
        try:
            return self.validation_service.sources(draft_id)
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def validation_runs(self, draft_id: str) -> list[dict[str, Any]]:
        try:
            return self.validation_service.list_runs(draft_id)
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def create_validation_run(
        self,
        draft_id: str,
        payload: ClassificationStandardSampleValidationRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.validation_service.create_run(
                draft_id,
                payload.expected_revision,
                payload.source_result_version_id,
                payload.sample_size,
                str(user["id"]),
                comparison_type=payload.comparison_type,
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def validation_run(self, run_id: str) -> dict[str, Any]:
        try:
            return self.validation_service.get(run_id)
        except ValueError as exc:
            raise self.handle_error(exc) from exc

    def approve_validation_run(
        self,
        run_id: str,
        payload: ClassificationStandardValidationApprovalRequest,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.validation_service.approve(
                run_id, payload.expected_revision, payload.note, str(user["id"])
            )
        except ValueError as exc:
            raise self.handle_error(exc) from exc


def register_validation_routes(
    router: APIRouter,
    validation_service: ClassificationStandardValidationService,
    current_user: Callable[..., dict[str, Any]],
    handle_error: Callable[[ValueError], HTTPException],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]
    operations = _ValidationOperations(validation_service, handle_error)

    @router.get("/api/classification-standard-drafts/{draft_id}/validation-sources")
    def validation_sources(draft_id: str, _user: User) -> list[dict[str, Any]]:
        return operations.validation_sources(draft_id)

    @router.get("/api/classification-standard-drafts/{draft_id}/validation-runs")
    def validation_runs(draft_id: str, _user: User) -> list[dict[str, Any]]:
        return operations.validation_runs(draft_id)

    @router.post(
        "/api/classification-standard-drafts/{draft_id}/validation-runs",
        status_code=201,
    )
    def create_validation_run(
        draft_id: str,
        payload: ClassificationStandardSampleValidationRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.create_validation_run(draft_id, payload, user)

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
        return operations.validation_run(run_id)

    @router.post("/api/classification-standard-validation-runs/{run_id}/approve")
    def approve_validation_run(
        run_id: str,
        payload: ClassificationStandardValidationApprovalRequest,
        user: User,
    ) -> dict[str, Any]:
        return operations.approve_validation_run(run_id, payload, user)
