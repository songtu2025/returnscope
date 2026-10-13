from typing import Annotated, Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from web_backend.database import Database
from web_backend.delivery_lifecycle import (
    DeliveryLifecycleConflict,
    DeliveryLifecycleService,
)


class DeliveryActionRequest(BaseModel):
    action: Literal["delete", "restore"]
    expected_revision: int = Field(ge=1)


def register_delivery_actions(
    router: APIRouter,
    database: Callable[[], Database],
    current_user: Callable[..., dict[str, Any]],
    *,
    kind: str,
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]
    path = (
        "/api/classification-results/{object_id}/lifecycle"
        if kind == "result"
        else "/api/analysis-dashboards/{object_id}/lifecycle"
    )

    @router.post(path)
    def change_lifecycle(
        object_id: str, payload: DeliveryActionRequest, user: User
    ) -> dict[str, bool]:
        try:
            service = DeliveryLifecycleService(database())
            action = service.result if kind == "result" else service.dashboard
            action(
                object_id,
                revision=payload.expected_revision,
                deleted=payload.action == "delete",
                actor=str(user["id"]),
            )
            return {"ok": True}
        except DeliveryLifecycleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def register_report_cancel(
    router: APIRouter,
    database: Callable[[], Database],
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/ai-insight-reports/{report_id}/cancel")
    def cancel_report(report_id: str, user: User) -> dict[str, bool]:
        try:
            service = DeliveryLifecycleService(database())
            service.cancel_report(report_id, str(user["id"]))
            return {"ok": True}
        except DeliveryLifecycleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
