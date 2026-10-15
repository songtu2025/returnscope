from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from web_backend.api_contracts.reviews import ReviewResolveRequest
from web_backend.common import list_audit
from web_backend.database import Database
from web_backend.review_contracts import LEGACY_REVIEW_BATCH_MESSAGE
from web_backend.review_service import (
    ReviewService,
    RevisionConflict,
)


def create_review_router(
    review_service: ReviewService,
    database: Database,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    _register_review_records(router, review_service, current_user)
    _register_review_batches(router, review_service, current_user)
    _register_review_batch_changes(router, review_service, current_user)
    _register_review_reference_routes(router, review_service, database, current_user)
    return router


def _register_review_records(
    router: APIRouter,
    review_service: ReviewService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/reviews")
    def list_reviews(
        _user: User,
        workflow_status: str | None = Query(default=None),
        task_id: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        return review_service.list(workflow_status, task_id)

    @router.get("/api/reviews/{review_id}")
    def get_review(review_id: str, _user: User) -> dict[str, Any]:
        item = review_service.get(review_id)
        if item is None:
            raise HTTPException(status_code=404, detail="复核记录不存在")
        return item

    @router.patch("/api/reviews/{review_id}")
    def resolve_review(
        review_id: str,
        payload: ReviewResolveRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return review_service.resolve(
                review_id=review_id,
                actor_id=str(user["id"]),
                **payload.model_dump(),
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _register_review_batches(
    router: APIRouter,
    review_service: ReviewService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post(
        "/api/classification-results/{version_id}/review-batches",
        status_code=410,
        deprecated=True,
    )
    def create_review_batch(version_id: str, user: User) -> None:
        raise HTTPException(status_code=410, detail=LEGACY_REVIEW_BATCH_MESSAGE)

    @router.get("/api/review-batches")
    def list_review_batches(
        _user: User,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        status: str | None = Query(default=None),
        base_result_version_id: str | None = Query(default=None),
        q: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return review_service.list_batches(
                page=page,
                page_size=page_size,
                status=status,
                base_result_version_id=base_result_version_id,
                q=q,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/review-batches/{batch_id}")
    def get_review_batch(batch_id: str, _user: User) -> dict[str, Any]:
        try:
            return review_service.get_batch(batch_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/review-batches/{batch_id}/records")
    def list_review_batch_records(
        batch_id: str,
        _user: User,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        workflow_status: str | None = Query(default=None),
        q: str | None = Query(default=None),
        listing: str | None = Query(default=None),
        product_name: str | None = Query(default=None),
        product_sku: str | None = Query(default=None),
        order_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            return review_service.batch_records(
                batch_id,
                page=page,
                page_size=page_size,
                workflow_status=workflow_status,
                q=q,
                listing=listing,
                product_name=product_name,
                product_sku=product_sku,
                order_id=order_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def _register_review_batch_changes(
    router: APIRouter,
    review_service: ReviewService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.patch(
        "/api/review-batches/{batch_id}/records/{review_id}",
        status_code=410,
        deprecated=True,
    )
    def update_review_batch_record(batch_id: str, review_id: str, user: User) -> None:
        raise HTTPException(status_code=410, detail=LEGACY_REVIEW_BATCH_MESSAGE)

    @router.patch(
        "/api/review-batches/{batch_id}/records", status_code=410, deprecated=True
    )
    def update_review_batch_records(batch_id: str, user: User) -> None:
        raise HTTPException(status_code=410, detail=LEGACY_REVIEW_BATCH_MESSAGE)

    @router.post(
        "/api/review-batches/{batch_id}/publish", status_code=410, deprecated=True
    )
    def publish_review_batch(batch_id: str, user: User) -> None:
        raise HTTPException(status_code=410, detail=LEGACY_REVIEW_BATCH_MESSAGE)


def _register_review_reference_routes(
    router: APIRouter,
    review_service: ReviewService,
    database: Database,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/taxonomy")
    def taxonomy(_user: User) -> dict[str, Any]:
        config = review_service.standard_service.combined_taxonomy()
        return config.model_dump(mode="json")

    @router.get("/api/audit/{entity_type}/{entity_id}")
    def audit(entity_type: str, entity_id: str, _user: User) -> list[dict[str, Any]]:
        return list_audit(database, entity_type, entity_id)
