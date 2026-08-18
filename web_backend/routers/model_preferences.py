from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.api_schemas import UserModelPreferenceRequest
from web_backend.model_preference_service import ModelPreferenceService


def create_model_preference_router(
    service: ModelPreferenceService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/model-preferences/me")
    def get_preference(user: User) -> dict[str, Any] | None:
        return service.get(str(user["id"]))

    @router.put("/api/model-preferences/me")
    def save_preference(
        payload: UserModelPreferenceRequest,
        user: User,
    ) -> dict[str, Any]:
        try:
            return service.save(str(user["id"]), **payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
