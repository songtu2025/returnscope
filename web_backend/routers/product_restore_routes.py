from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.api_contracts.datasets import ProductRestoreRequest
from web_backend.dataset_service import DatasetRevisionConflict, DatasetService
from web_backend.datasets.product_restore import restore_product_edit


def register_product_restore(
    router: APIRouter,
    dataset_service: DatasetService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/datasets/{dataset_id}/changes/{audit_id}/restore")
    def restore_product_change(
        dataset_id: str, audit_id: str, payload: ProductRestoreRequest, user: User
    ) -> dict[str, Any]:
        try:
            return restore_product_edit(
                dataset_service,
                dataset_id,
                audit_id,
                payload.expected_version,
                str(user["id"]),
            )
        except DatasetRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
